-- =============================================================================
-- Data-integrity audit. One row per invariant; `violations` must be 0 for all.
-- Run by `python -m mealsub verify` and automatically after every build.
-- =============================================================================
SELECT 'orders_outside_subscription_window' AS check_name, COUNT(*) AS violations
FROM orders o
JOIN subscriptions s ON s.subscription_id = o.subscription_id
WHERE o.delivery_date < s.start_date
   OR (s.end_date IS NOT NULL AND o.delivery_date >= s.end_date)
   OR o.delivery_date > (SELECT value FROM meta WHERE key = 'as_of_date')

UNION ALL
SELECT 'orders_inside_a_pause', COUNT(*)
FROM orders o
JOIN subscription_pauses p ON p.subscription_id = o.subscription_id
 AND o.delivery_date >= p.pause_start AND o.delivery_date < p.pause_end

UNION ALL
SELECT 'pauses_outside_subscription_window', COUNT(*)
FROM subscription_pauses p
JOIN subscriptions s ON s.subscription_id = p.subscription_id
WHERE p.pause_start < s.start_date
   OR p.pause_end > COALESCE(s.end_date,
        date((SELECT value FROM meta WHERE key = 'as_of_date'), '+1 day'))

UNION ALL
SELECT 'overlapping_pauses', COUNT(*)
FROM subscription_pauses a
JOIN subscription_pauses b ON a.subscription_id = b.subscription_id
 AND a.pause_id < b.pause_id
 AND a.pause_start < b.pause_end AND a.pause_end > b.pause_start

UNION ALL
SELECT 'overlapping_subscriptions_per_customer', COUNT(*)
FROM subscriptions a
JOIN subscriptions b ON a.customer_id = b.customer_id
 AND a.subscription_id < b.subscription_id
 AND a.start_date < COALESCE(b.end_date, '9999-12-31')
 AND b.start_date < COALESCE(a.end_date, '9999-12-31')

UNION ALL
SELECT 'signup_date_differs_from_first_subscription', COUNT(*)
FROM customers c
WHERE c.signup_date IS NOT (SELECT MIN(s.start_date) FROM subscriptions s
                            WHERE s.customer_id = c.customer_id)

UNION ALL
SELECT 'order_item_meal_type_not_in_plan', COUNT(*)
FROM order_items oi
JOIN orders o        ON o.order_id = oi.order_id
JOIN subscriptions s ON s.subscription_id = o.subscription_id
JOIN meals m         ON m.meal_id = oi.meal_id
WHERE NOT EXISTS (SELECT 1 FROM plan_slots ps
                  WHERE ps.plan_id = s.plan_id AND ps.meal_type = m.meal_type)

UNION ALL
SELECT 'order_not_exactly_one_meal_per_plan_slot', COUNT(*)
FROM orders o
JOIN subscriptions s ON s.subscription_id = o.subscription_id
WHERE (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id = o.order_id)
      <> (SELECT COUNT(*) FROM plan_slots ps WHERE ps.plan_id = s.plan_id)
   OR (SELECT COUNT(DISTINCT m.meal_type)
       FROM order_items oi JOIN meals m ON m.meal_id = oi.meal_id
       WHERE oi.order_id = o.order_id)
      <> (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id = o.order_id)

UNION ALL
SELECT 'order_amount_differs_from_plan_price', COUNT(*)
FROM orders o
JOIN subscriptions s ON s.subscription_id = o.subscription_id
JOIN plans p         ON p.plan_id = s.plan_id
WHERE o.delivery_status <> 'failed' AND o.amount_cents <> p.price_per_day_cents

UNION ALL
SELECT 'rating_on_failed_order', COUNT(*)
FROM meal_ratings r
JOIN order_items oi ON oi.order_item_id = r.order_item_id
JOIN orders o       ON o.order_id = oi.order_id
WHERE o.delivery_status = 'failed'

UNION ALL
SELECT 'rating_dated_before_delivery', COUNT(*)
FROM meal_ratings r
JOIN order_items oi ON oi.order_item_id = r.order_item_id
JOIN orders o       ON o.order_id = oi.order_id
WHERE r.rated_at < o.delivery_date

UNION ALL
SELECT 'rating_dated_after_as_of', COUNT(*)
FROM meal_ratings r
WHERE r.rated_at > (SELECT value FROM meta WHERE key = 'as_of_date')

UNION ALL
SELECT 'allergen_served_to_allergic_customer', COUNT(*)
FROM order_items oi
JOIN orders o           ON o.order_id = oi.order_id
JOIN subscriptions s    ON s.subscription_id = o.subscription_id
JOIN v_meal_allergens ma ON ma.meal_id = oi.meal_id
JOIN customer_allergens ca ON ca.customer_id = s.customer_id
 AND ca.allergen_id = ma.allergen_id

UNION ALL
SELECT 'disliked_ingredient_served', COUNT(*)
FROM order_items oi
JOIN orders o           ON o.order_id = oi.order_id
JOIN subscriptions s    ON s.subscription_id = o.subscription_id
JOIN meal_ingredients mi ON mi.meal_id = oi.meal_id
JOIN customer_dislikes cd ON cd.customer_id = s.customer_id
 AND cd.ingredient_id = mi.ingredient_id
