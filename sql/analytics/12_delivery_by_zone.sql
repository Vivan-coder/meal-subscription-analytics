-- 12 | Delivery reliability, satisfaction and churn by delivery zone
-- Joins three independent aggregates (orders, ratings, cancellations) on zone.
-- Techniques: CTE per fact table, then a single join (avoids the fan-out you
-- would get from joining orders, ratings and subscriptions in one pass).
WITH order_stats AS (
    SELECT c.zone_id,
           COUNT(*)                            AS orders,
           SUM(o.delivery_status = 'late')     AS late,
           SUM(o.delivery_status = 'failed')   AS failed
    FROM orders o
    JOIN subscriptions s ON s.subscription_id = o.subscription_id
    JOIN customers c     ON c.customer_id = s.customer_id
    GROUP BY c.zone_id
),
rating_stats AS (
    SELECT c.zone_id, COUNT(*) AS n_ratings, AVG(mr.rating) AS avg_rating
    FROM meal_ratings mr
    JOIN order_items oi  ON oi.order_item_id = mr.order_item_id
    JOIN orders o        ON o.order_id = oi.order_id
    JOIN subscriptions s ON s.subscription_id = o.subscription_id
    JOIN customers c     ON c.customer_id = s.customer_id
    GROUP BY c.zone_id
),
cancel_stats AS (
    SELECT c.zone_id,
           COUNT(*)                                   AS cancellations,
           SUM(s.cancel_reason = 'delivery_issues')   AS delivery_cancellations
    FROM subscriptions s
    JOIN customers c ON c.customer_id = s.customer_id
    WHERE s.end_date IS NOT NULL
    GROUP BY c.zone_id
)
SELECT z.name                                              AS zone,
       os.orders,
       ROUND(100.0 * os.late   / os.orders, 2)             AS late_pct,
       ROUND(100.0 * os.failed / os.orders, 2)             AS failed_pct,
       ROUND(rs.avg_rating, 2)                             AS avg_rating,
       cs.cancellations,
       ROUND(100.0 * cs.delivery_cancellations / cs.cancellations, 1)
                                                           AS cancelled_for_delivery_pct
FROM zones z
JOIN order_stats os  ON os.zone_id = z.zone_id
JOIN rating_stats rs ON rs.zone_id = z.zone_id
JOIN cancel_stats cs ON cs.zone_id = z.zone_id
ORDER BY late_pct DESC;
