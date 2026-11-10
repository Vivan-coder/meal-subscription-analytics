-- Personal taste signal: how much does THIS customer rate each cuisine above or
-- below their own average? Shrunk toward 0 with a prior of 3 pseudo-ratings so a
-- single 5-star rating does not dominate.
--   affinity = (n * (cuisine_avg - overall_avg)) / (n + 3)
-- Params: :customer_id
WITH mine AS (
    SELECT m.cuisine, mr.rating
    FROM meal_ratings mr
    JOIN order_items oi  ON oi.order_item_id = mr.order_item_id
    JOIN orders o        ON o.order_id = oi.order_id
    JOIN subscriptions s ON s.subscription_id = o.subscription_id
    JOIN meals m         ON m.meal_id = oi.meal_id
    WHERE s.customer_id = :customer_id
),
overall AS (SELECT AVG(rating) AS mu FROM mine)
SELECT cuisine,
       COUNT(*) AS n,
       COUNT(*) * (AVG(rating) - (SELECT mu FROM overall)) / (COUNT(*) + 3.0) AS affinity
FROM mine
GROUP BY cuisine;
