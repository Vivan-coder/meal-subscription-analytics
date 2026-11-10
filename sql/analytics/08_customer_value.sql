-- 08 | Customer value to date by acquisition channel
-- "LTV to date" = cumulative revenue per customer so far (not a forecast).
-- Techniques: correlated aggregates in a CTE, EXISTS flag, AVG over booleans.
WITH params AS (SELECT date(value, '+1 day') AS horizon FROM meta WHERE key = 'as_of_date'),
cust AS (
    SELECT c.customer_id, c.acquisition_channel,
           COALESCE((SELECT SUM(o.amount_cents)
                     FROM orders o JOIN subscriptions s ON s.subscription_id = o.subscription_id
                     WHERE s.customer_id = c.customer_id), 0)           AS revenue_cents,
           (SELECT SUM(julianday(COALESCE(s.end_date, p.horizon)) - julianday(s.start_date))
            FROM subscriptions s, params p
            WHERE s.customer_id = c.customer_id)                        AS subscribed_days,
           EXISTS (SELECT 1 FROM subscriptions s
                   WHERE s.customer_id = c.customer_id AND s.end_date IS NULL) AS is_active
    FROM customers c
)
SELECT acquisition_channel                         AS channel,
       COUNT(*)                                    AS customers,
       ROUND(AVG(revenue_cents) / 100.0, 2)        AS avg_ltv_to_date_usd,
       ROUND(AVG(subscribed_days), 1)              AS avg_days_subscribed,
       ROUND(100.0 * AVG(is_active), 1)            AS still_active_pct,
       ROUND(SUM(revenue_cents) / 100.0, 0)        AS total_revenue_usd
FROM cust
GROUP BY acquisition_channel
ORDER BY avg_ltv_to_date_usd DESC;
