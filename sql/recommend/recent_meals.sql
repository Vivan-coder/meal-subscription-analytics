-- Meals the customer was served in the 14 days before the planned week.
-- The recommender penalises (does not forbid) these to keep the menu varied.
-- Params: :customer_id, :since   (ISO date, e.g. plan start minus 14 days)
SELECT DISTINCT oi.meal_id
FROM order_items oi
JOIN orders o        ON o.order_id = oi.order_id
JOIN subscriptions s ON s.subscription_id = o.subscription_id
WHERE s.customer_id = :customer_id
  AND o.delivery_date >= :since;
