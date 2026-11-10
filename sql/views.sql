-- =============================================================================
-- Reusable views. Every analytics query is built on these definitions so a
-- business metric is defined in exactly one place.
-- =============================================================================

-- Meal nutrition is derived from ingredient grams (single source of truth).
CREATE VIEW v_meal_nutrition AS
SELECT m.meal_id,
       ROUND(SUM(mi.grams / 100.0 * i.kcal_per_100g),    1) AS calories,
       ROUND(SUM(mi.grams / 100.0 * i.protein_per_100g), 1) AS protein_g,
       ROUND(SUM(mi.grams / 100.0 * i.carbs_per_100g),   1) AS carbs_g,
       ROUND(SUM(mi.grams / 100.0 * i.fat_per_100g),     1) AS fat_g
FROM meals m
JOIN meal_ingredients mi ON mi.meal_id = m.meal_id
JOIN ingredients i       ON i.ingredient_id = mi.ingredient_id
GROUP BY m.meal_id;

-- Allergens present in a meal (via its ingredients).
CREATE VIEW v_meal_allergens AS
SELECT DISTINCT mi.meal_id, ia.allergen_id
FROM meal_ingredients mi
JOIN ingredient_allergens ia ON ia.ingredient_id = mi.ingredient_id;

-- Days a subscription was "at risk" of cancelling: calendar days subscribed
-- (through as_of for active ones) minus paused days. Basis of every churn rate.
CREATE VIEW v_subscription_exposure AS
SELECT s.subscription_id,
       s.customer_id,
       CAST(julianday(COALESCE(s.end_date,
                 date((SELECT value FROM meta WHERE key = 'as_of_date'), '+1 day')))
            - julianday(s.start_date) AS INTEGER)
       - COALESCE((SELECT SUM(CAST(julianday(p.pause_end) - julianday(p.pause_start) AS INTEGER))
                   FROM subscription_pauses p
                   WHERE p.subscription_id = s.subscription_id), 0) AS exposure_days
FROM subscriptions s;

-- Bayesian-shrunk meal rating: a meal with few ratings is pulled toward the
-- global mean. Prior strength m = 20 pseudo-ratings.
--   shrunk = (n * avg + 20 * global_avg) / (n + 20)
CREATE VIEW v_meal_rating AS
WITH g AS (SELECT AVG(rating) AS mu FROM meal_ratings),
     r AS (SELECT oi.meal_id, COUNT(*) AS n, AVG(mr.rating) AS avg_rating
           FROM meal_ratings mr
           JOIN order_items oi ON oi.order_item_id = mr.order_item_id
           GROUP BY oi.meal_id)
SELECT m.meal_id,
       COALESCE(r.n, 0) AS n_ratings,
       r.avg_rating,
       (COALESCE(r.n, 0) * COALESCE(r.avg_rating, 0) + 20.0 * g.mu)
         / (COALESCE(r.n, 0) + 20.0) AS shrunk_rating
FROM meals m
CROSS JOIN g
LEFT JOIN r ON r.meal_id = m.meal_id;
