-- 01 | Monthly business scorecard
-- Revenue, subscriber base, growth and delivery quality per calendar month.
--   active_subscribers : subscriptions active at month end (start <= eom < end)
--   arpu_usd           : revenue / customers who received at least one order that month
--   mom_growth_pct     : revenue growth vs the previous month (window function LAG)
-- Techniques: recursive CTE (month spine), window functions, conditional aggregation.
WITH RECURSIVE
params AS (
    SELECT date(value) AS as_of FROM meta WHERE key = 'as_of_date'
),
months(month_start) AS (
    SELECT date(MIN(start_date), 'start of month') FROM subscriptions
    UNION ALL
    SELECT date(month_start, '+1 month') FROM months
    WHERE date(month_start, '+1 month') <= (SELECT as_of FROM params)
),
spine AS (
    SELECT strftime('%Y-%m', month_start) AS ym,
           month_start,
           MIN(date(month_start, '+1 month', '-1 day'), (SELECT as_of FROM params)) AS month_end
    FROM months
),
order_stats AS (
    SELECT strftime('%Y-%m', o.delivery_date) AS ym,
           COUNT(*)                                    AS orders,
           SUM(o.amount_cents)                         AS revenue_cents,
           SUM(o.delivery_status = 'on_time')          AS on_time_orders,
           SUM(o.delivery_status = 'failed')           AS failed_orders,
           COUNT(DISTINCT s.customer_id)               AS ordering_customers
    FROM orders o
    JOIN subscriptions s ON s.subscription_id = o.subscription_id
    GROUP BY 1
),
sub_stats AS (
    SELECT sp.ym,
           (SELECT COUNT(*) FROM subscriptions s
            WHERE s.start_date <= sp.month_end
              AND (s.end_date IS NULL OR s.end_date > sp.month_end))        AS active_subscribers,
           (SELECT COUNT(*) FROM customers c
            WHERE strftime('%Y-%m', c.signup_date) = sp.ym)                 AS new_customers,
           (SELECT COUNT(*) FROM subscriptions s
            WHERE strftime('%Y-%m', s.start_date) = sp.ym
              AND s.start_date > (SELECT c.signup_date FROM customers c
                                  WHERE c.customer_id = s.customer_id))     AS reactivations,
           (SELECT COUNT(*) FROM subscriptions s
            WHERE strftime('%Y-%m', s.end_date) = sp.ym)                    AS cancellations
    FROM spine sp
)
SELECT sp.ym                                              AS month,
       ss.active_subscribers,
       ss.new_customers,
       ss.reactivations,
       ss.cancellations,
       COALESCE(os.orders, 0)                             AS orders,
       ROUND(COALESCE(os.revenue_cents, 0) / 100.0, 2)    AS revenue_usd,
       ROUND(100.0 * (os.revenue_cents - LAG(os.revenue_cents) OVER w)
             / LAG(os.revenue_cents) OVER w, 1)           AS mom_growth_pct,
       ROUND(os.revenue_cents / 100.0 / os.ordering_customers, 2) AS arpu_usd,
       ROUND(100.0 * os.on_time_orders / os.orders, 1)    AS on_time_pct,
       ROUND(100.0 * os.failed_orders  / os.orders, 1)    AS failed_pct
FROM spine sp
JOIN sub_stats ss ON ss.ym = sp.ym
LEFT JOIN order_stats os ON os.ym = sp.ym
WINDOW w AS (ORDER BY sp.ym)
ORDER BY sp.ym;
