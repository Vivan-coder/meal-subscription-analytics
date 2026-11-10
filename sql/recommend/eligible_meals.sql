-- Meals a customer may be served: HARD constraints are applied in SQL.
--   * the meal's type is one of the slots in the customer's plan
--   * the meal contains none of the customer's allergens   (NOT EXISTS anti-join)
--   * the meal contains none of the customer's disliked ingredients
-- Nutrition comes from v_meal_nutrition (derived from ingredient grams).
-- Params: :customer_id, :plan_id
SELECT m.meal_id,
       m.name,
       m.cuisine,
       m.meal_type,
       n.calories,
       n.protein_g
FROM meals m
JOIN v_meal_nutrition n ON n.meal_id = m.meal_id
WHERE m.meal_type IN (SELECT ps.meal_type FROM plan_slots ps WHERE ps.plan_id = :plan_id)
  AND NOT EXISTS (
        SELECT 1
        FROM v_meal_allergens ma
        JOIN customer_allergens ca ON ca.allergen_id = ma.allergen_id
        WHERE ma.meal_id = m.meal_id AND ca.customer_id = :customer_id)
  AND NOT EXISTS (
        SELECT 1
        FROM meal_ingredients mi
        JOIN customer_dislikes cd ON cd.ingredient_id = mi.ingredient_id
        WHERE mi.meal_id = m.meal_id AND cd.customer_id = :customer_id)
ORDER BY m.meal_type, m.meal_id;
