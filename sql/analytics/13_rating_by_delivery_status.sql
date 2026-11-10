-- 13 | How much does a late delivery hurt the rating?
-- Failed deliveries are refunded and cannot be rated, so only on_time and late
-- orders appear. Techniques: boolean aggregation, joins across the fact chain.
SELECT o.delivery_status,
       COUNT(*)                                               AS rated_items,
       ROUND(AVG(mr.rating), 2)                               AS avg_rating,
       ROUND(100.0 * SUM(mr.rating <= 2) / COUNT(*), 1)       AS low_rating_pct,
       ROUND(100.0 * SUM(mr.feedback_tag = 'cold_on_arrival') / COUNT(*), 1)
                                                              AS cold_on_arrival_pct
FROM meal_ratings mr
JOIN order_items oi ON oi.order_item_id = mr.order_item_id
JOIN orders o       ON o.order_id = oi.order_id
GROUP BY o.delivery_status
ORDER BY avg_rating DESC;
