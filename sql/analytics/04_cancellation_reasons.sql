-- 04 | Why do subscribers cancel?
-- Reason mix, how long they stayed, and what share cancelled within 30 days.
-- Techniques: window function for share-of-total, conditional aggregation.
SELECT cancel_reason                                              AS reason,
       COUNT(*)                                                   AS cancellations,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)         AS share_pct,
       ROUND(AVG(julianday(end_date) - julianday(start_date)), 1) AS avg_days_subscribed,
       ROUND(100.0 * SUM(julianday(end_date) - julianday(start_date) <= 30) / COUNT(*), 1)
                                                                  AS cancelled_within_30d_pct
FROM subscriptions
WHERE end_date IS NOT NULL
GROUP BY cancel_reason
ORDER BY cancellations DESC;
