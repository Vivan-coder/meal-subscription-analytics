-- =============================================================================
-- Temporal-integrity triggers (rules CHECK constraints cannot express).
-- Installed after the bulk load (see mealsub/generate.py): the load is audited
-- by the set-based queries in sql/checks/integrity.sql, then these triggers
-- guard every later write. tests/test_schema.py exercises each one.
-- =============================================================================
-- Orders must fall inside the subscription window, on or before the dataset's
-- as_of date, and never inside a pause.
CREATE TRIGGER trg_orders_valid
BEFORE INSERT ON orders
BEGIN
    SELECT RAISE(ABORT, 'order outside subscription window')
    WHERE NOT EXISTS (
        SELECT 1 FROM subscriptions s
        WHERE s.subscription_id = NEW.subscription_id
          AND NEW.delivery_date >= s.start_date
          AND (s.end_date IS NULL OR NEW.delivery_date < s.end_date)
          AND NEW.delivery_date <= (SELECT value FROM meta WHERE key = 'as_of_date')
    );
    SELECT RAISE(ABORT, 'order falls inside a pause')
    WHERE EXISTS (
        SELECT 1 FROM subscription_pauses p
        WHERE p.subscription_id = NEW.subscription_id
          AND NEW.delivery_date >= p.pause_start
          AND NEW.delivery_date <  p.pause_end
    );
END;

-- Pauses must sit inside the subscription window and may not overlap each other.
CREATE TRIGGER trg_pauses_valid
BEFORE INSERT ON subscription_pauses
BEGIN
    SELECT RAISE(ABORT, 'pause outside subscription window')
    WHERE NOT EXISTS (
        SELECT 1 FROM subscriptions s
        WHERE s.subscription_id = NEW.subscription_id
          AND NEW.pause_start >= s.start_date
          AND NEW.pause_end <= COALESCE(
                s.end_date,
                date((SELECT value FROM meta WHERE key = 'as_of_date'), '+1 day'))
    );
    SELECT RAISE(ABORT, 'overlapping pause')
    WHERE EXISTS (
        SELECT 1 FROM subscription_pauses p
        WHERE p.subscription_id = NEW.subscription_id
          AND NEW.pause_start < p.pause_end
          AND NEW.pause_end   > p.pause_start
    );
END;

-- An order may only contain meals for slots the plan delivers, once per slot.
CREATE TRIGGER trg_order_items_valid
BEFORE INSERT ON order_items
BEGIN
    SELECT RAISE(ABORT, 'meal type not part of the subscription plan')
    WHERE NOT EXISTS (
        SELECT 1
        FROM orders o
        JOIN subscriptions s ON s.subscription_id = o.subscription_id
        JOIN meals m         ON m.meal_id = NEW.meal_id
        JOIN plan_slots ps   ON ps.plan_id = s.plan_id AND ps.meal_type = m.meal_type
        WHERE o.order_id = NEW.order_id
    );
    SELECT RAISE(ABORT, 'order already has a meal for this slot')
    WHERE EXISTS (
        SELECT 1
        FROM order_items oi
        JOIN meals m_old ON m_old.meal_id = oi.meal_id
        JOIN meals m_new ON m_new.meal_id = NEW.meal_id
        WHERE oi.order_id = NEW.order_id AND m_old.meal_type = m_new.meal_type
    );
END;

-- Ratings: only for delivered items, never before delivery, never after as_of.
CREATE TRIGGER trg_ratings_valid
BEFORE INSERT ON meal_ratings
BEGIN
    SELECT RAISE(ABORT, 'cannot rate an undelivered (failed) order')
    WHERE EXISTS (
        SELECT 1 FROM order_items oi JOIN orders o ON o.order_id = oi.order_id
        WHERE oi.order_item_id = NEW.order_item_id AND o.delivery_status = 'failed'
    );
    SELECT RAISE(ABORT, 'rating dated before delivery')
    WHERE EXISTS (
        SELECT 1 FROM order_items oi JOIN orders o ON o.order_id = oi.order_id
        WHERE oi.order_item_id = NEW.order_item_id AND NEW.rated_at < o.delivery_date
    );
    SELECT RAISE(ABORT, 'rating dated after the dataset as_of date')
    WHERE NEW.rated_at > (SELECT value FROM meta WHERE key = 'as_of_date');
END;
