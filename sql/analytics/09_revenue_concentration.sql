-- 09 | Revenue concentration (Pareto) by customer decile
-- Decile 1 = the top 10% of customers by lifetime revenue.
-- Techniques: NTILE, running total with a window frame.
WITH cust AS (
    SELECT s.customer_id, SUM(o.amount_cents) AS revenue_cents
    FROM orders o JOIN subscriptions s ON s.subscription_id = o.subscription_id
    GROUP BY s.customer_id
),
ranked AS (
    SELECT customer_id, revenue_cents,
           NTILE(10) OVER (ORDER BY revenue_cents DESC, customer_id) AS decile
    FROM cust
),
agg AS (
    SELECT decile, COUNT(*) AS customers, SUM(revenue_cents) AS revenue_cents,
           MIN(revenue_cents) AS min_cents, MAX(revenue_cents) AS max_cents
    FROM ranked GROUP BY decile
)
SELECT decile,
       customers,
       ROUND(revenue_cents / 100.0, 0)                                   AS revenue_usd,
       ROUND(100.0 * revenue_cents / SUM(revenue_cents) OVER (), 1)      AS share_pct,
       ROUND(100.0 * SUM(revenue_cents) OVER (ORDER BY decile
             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
             / SUM(revenue_cents) OVER (), 1)                            AS cumulative_share_pct,
       ROUND(min_cents / 100.0, 0)                                       AS min_customer_usd,
       ROUND(max_cents / 100.0, 0)                                       AS max_customer_usd
FROM agg
ORDER BY decile;
