-- =============================================================================
-- Meal-subscription schema (SQLite 3.35+)
--
-- Conventions
--   * Dates are ISO-8601 text ('YYYY-MM-DD'); money is integer US cents.
--   * A subscription is active on every day d with start_date <= d < end_date
--     (end_date = the cancellation date; NULL while still active).
--   * A pause covers pause_start <= d < pause_end (no deliveries, no billing).
--   * Business rules that CHECK constraints cannot express (temporal integrity)
--     are enforced by triggers, so bad data is rejected at write time.
-- =============================================================================
PRAGMA foreign_keys = ON;

-- Simulation / dataset metadata (as_of_date is the "today" of the dataset).
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ------------------------------------------------------------------ catalog --
CREATE TABLE zones (
    zone_id INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE
);

CREATE TABLE allergens (
    allergen_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE
);

CREATE TABLE ingredients (
    ingredient_id    INTEGER PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    category         TEXT NOT NULL
        CHECK (category IN ('protein','dairy','carb','fruit','vegetable','fat','other')),
    kcal_per_100g    REAL NOT NULL CHECK (kcal_per_100g    >= 0),
    protein_per_100g REAL NOT NULL CHECK (protein_per_100g >= 0),
    carbs_per_100g   REAL NOT NULL CHECK (carbs_per_100g   >= 0),
    fat_per_100g     REAL NOT NULL CHECK (fat_per_100g     >= 0)
);

CREATE TABLE ingredient_allergens (
    ingredient_id INTEGER NOT NULL REFERENCES ingredients(ingredient_id),
    allergen_id   INTEGER NOT NULL REFERENCES allergens(allergen_id),
    PRIMARY KEY (ingredient_id, allergen_id)
) WITHOUT ROWID;

CREATE TABLE meals (
    meal_id   INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    cuisine   TEXT NOT NULL,
    meal_type TEXT NOT NULL CHECK (meal_type IN ('breakfast','lunch','dinner','snack'))
);

CREATE TABLE meal_ingredients (
    meal_id       INTEGER NOT NULL REFERENCES meals(meal_id),
    ingredient_id INTEGER NOT NULL REFERENCES ingredients(ingredient_id),
    grams         REAL    NOT NULL CHECK (grams > 0),
    PRIMARY KEY (meal_id, ingredient_id)
) WITHOUT ROWID;
CREATE INDEX idx_meal_ingredients_ingredient ON meal_ingredients(ingredient_id);

CREATE TABLE plans (
    plan_id            INTEGER PRIMARY KEY,
    name               TEXT    NOT NULL UNIQUE,
    price_per_day_cents INTEGER NOT NULL CHECK (price_per_day_cents > 0)
);

-- Which meal slots a plan delivers every delivery day.
CREATE TABLE plan_slots (
    plan_id   INTEGER NOT NULL REFERENCES plans(plan_id),
    meal_type TEXT    NOT NULL CHECK (meal_type IN ('breakfast','lunch','dinner','snack')),
    PRIMARY KEY (plan_id, meal_type)
) WITHOUT ROWID;

-- ---------------------------------------------------------------- customers --
CREATE TABLE customers (
    customer_id         INTEGER PRIMARY KEY,
    full_name           TEXT NOT NULL,
    email               TEXT NOT NULL UNIQUE,
    zone_id             INTEGER NOT NULL REFERENCES zones(zone_id),
    signup_date         TEXT NOT NULL CHECK (date(signup_date) IS signup_date),
    acquisition_channel TEXT NOT NULL
        CHECK (acquisition_channel IN ('organic','referral','paid_social','promo')),
    goal                TEXT NOT NULL
        CHECK (goal IN ('lose_weight','maintain','build_muscle')),
    daily_calorie_target INTEGER NOT NULL CHECK (daily_calorie_target BETWEEN 1000 AND 3500),
    protein_target_g     INTEGER NOT NULL CHECK (protein_target_g > 0)
);
CREATE INDEX idx_customers_zone ON customers(zone_id);

CREATE TABLE customer_allergens (
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    allergen_id INTEGER NOT NULL REFERENCES allergens(allergen_id),
    PRIMARY KEY (customer_id, allergen_id)
) WITHOUT ROWID;

CREATE TABLE customer_dislikes (
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    ingredient_id INTEGER NOT NULL REFERENCES ingredients(ingredient_id),
    PRIMARY KEY (customer_id, ingredient_id)
) WITHOUT ROWID;

-- ------------------------------------------------------------ subscriptions --
CREATE TABLE subscriptions (
    subscription_id INTEGER PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    plan_id         INTEGER NOT NULL REFERENCES plans(plan_id),
    start_date      TEXT NOT NULL CHECK (date(start_date) IS start_date),
    end_date        TEXT CHECK (end_date IS NULL
                                OR (date(end_date) IS end_date AND end_date > start_date)),
    cancel_reason   TEXT CHECK (cancel_reason IN
        ('price','menu_variety','delivery_issues','goal_reached','relocation','other')),
    -- a subscription has a cancel reason if and only if it has been cancelled
    CHECK ((end_date IS NULL) = (cancel_reason IS NULL))
);
CREATE INDEX idx_subscriptions_customer ON subscriptions(customer_id, start_date);

CREATE TABLE subscription_pauses (
    pause_id        INTEGER PRIMARY KEY,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(subscription_id),
    pause_start     TEXT NOT NULL CHECK (date(pause_start) IS pause_start),
    pause_end       TEXT NOT NULL CHECK (date(pause_end)   IS pause_end),
    CHECK (pause_end > pause_start),
    UNIQUE (subscription_id, pause_start)
);

-- ------------------------------------------------------------------- orders --
-- One order = one delivery day for one subscription (Monday-Friday only).
-- Failed deliveries are refunded: amount_cents = 0 exactly when status = 'failed'.
CREATE TABLE orders (
    order_id        INTEGER PRIMARY KEY,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(subscription_id),
    delivery_date   TEXT NOT NULL CHECK (date(delivery_date) IS delivery_date),
    delivery_status TEXT NOT NULL CHECK (delivery_status IN ('on_time','late','failed')),
    amount_cents    INTEGER NOT NULL CHECK (amount_cents >= 0),
    UNIQUE (subscription_id, delivery_date),
    CHECK (CAST(strftime('%w', delivery_date) AS INTEGER) BETWEEN 1 AND 5),
    CHECK ((delivery_status = 'failed') = (amount_cents = 0))
);
CREATE INDEX idx_orders_date ON orders(delivery_date);

CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders(order_id),
    meal_id       INTEGER NOT NULL REFERENCES meals(meal_id),
    UNIQUE (order_id, meal_id)
);
CREATE INDEX idx_order_items_meal ON order_items(meal_id);

CREATE TABLE meal_ratings (
    order_item_id INTEGER PRIMARY KEY REFERENCES order_items(order_item_id),
    rating        INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    feedback_tag  TEXT CHECK (feedback_tag IN
        ('delicious','great_portion','bland','too_salty','portion_small','repetitive','cold_on_arrival')),
    rated_at      TEXT NOT NULL CHECK (date(rated_at) IS rated_at)
);

-- Output of the recommender (one row per customer, day and slot).
CREATE TABLE recommended_plans (
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    plan_date   TEXT    NOT NULL CHECK (date(plan_date) IS plan_date),
    meal_type   TEXT    NOT NULL CHECK (meal_type IN ('breakfast','lunch','dinner','snack')),
    meal_id     INTEGER NOT NULL REFERENCES meals(meal_id),
    PRIMARY KEY (customer_id, plan_date, meal_type)
) WITHOUT ROWID;
