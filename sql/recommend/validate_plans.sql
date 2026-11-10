-- Independent audit of the persisted recommendations (table recommended_plans).
-- Every `violations` value except calorie_days_outside_tolerance must be 0;
-- the calorie tolerance (default +/-10%) is a target the planner reports on.
-- Params: :tolerance (e.g. 0.10)
WITH day_totals AS (
    SELECT rp.customer_id, rp.plan_date,
           SUM(n.calories) AS kcal,
           c.daily_calorie_target AS target
    FROM recommended_plans rp
    JOIN v_meal_nutrition n ON n.meal_id = rp.meal_id
    JOIN customers c        ON c.customer_id = rp.customer_id
    GROUP BY rp.customer_id, rp.plan_date
)
SELECT 'allergen_in_plan' AS check_name, COUNT(*) AS violations
FROM recommended_plans rp
JOIN v_meal_allergens ma   ON ma.meal_id = rp.meal_id
JOIN customer_allergens ca ON ca.customer_id = rp.customer_id AND ca.allergen_id = ma.allergen_id

UNION ALL
SELECT 'disliked_ingredient_in_plan', COUNT(*)
FROM recommended_plans rp
JOIN meal_ingredients mi   ON mi.meal_id = rp.meal_id
JOIN customer_dislikes cd  ON cd.customer_id = rp.customer_id AND cd.ingredient_id = mi.ingredient_id

UNION ALL
SELECT 'slot_does_not_match_meal_type', COUNT(*)
FROM recommended_plans rp
JOIN meals m ON m.meal_id = rp.meal_id
WHERE m.meal_type <> rp.meal_type

UNION ALL
SELECT 'slot_not_in_customers_plan', COUNT(*)
FROM recommended_plans rp
WHERE NOT EXISTS (
    SELECT 1 FROM subscriptions s
    JOIN plan_slots ps ON ps.plan_id = s.plan_id
    WHERE s.customer_id = rp.customer_id AND s.end_date IS NULL
      AND ps.meal_type = rp.meal_type)

UNION ALL
SELECT 'meal_repeated_within_week', COUNT(*)
FROM (SELECT customer_id, meal_id FROM recommended_plans
      GROUP BY customer_id, meal_id HAVING COUNT(*) > 1)

UNION ALL
SELECT 'calorie_days_outside_tolerance', COUNT(*)
FROM day_totals
WHERE ABS(kcal - target) > :tolerance * target

UNION ALL
SELECT 'planned_customer_days', COUNT(*) FROM day_totals
