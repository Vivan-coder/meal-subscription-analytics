-- 02 | Cohort retention (long format)
-- A customer's cohort is the month of their FIRST subscription. They count as
-- retained at offset k if they hold an active subscription at the end of the
-- month that is k months after the cohort month (month 0 = signup month end).
-- Cells whose month-end lies after the dataset's as_of date are not reported.
-- Techniques: recursive CTE, date arithmetic, LEFT JOIN so a cohort that fully
-- churned shows 0 instead of vanishing.
WITH RECURSIVE
params AS (SELECT date(value) AS as_of FROM meta WHERE key = 'as_of_date'),
cohorts AS (
    SELECT customer_id, date(MIN(start_date), 'start of month') AS cohort_month
    FROM subscriptions
    GROUP BY customer_id
),
sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_size FROM cohorts GROUP BY cohort_month
),
offsets(k) AS (
    SELECT 0 UNION ALL SELECT k + 1 FROM offsets WHERE k < 36
),
grid AS (
    SELECT z.cohort_month, z.cohort_size, o.k,
           date(z.cohort_month, '+' || (o.k + 1) || ' months', '-1 day') AS month_end
    FROM sizes z
    JOIN offsets o
    WHERE date(z.cohort_month, '+' || (o.k + 1) || ' months', '-1 day')
          <= (SELECT as_of FROM params)
),
retained AS (
    SELECT g.cohort_month, g.k, COUNT(DISTINCT c.customer_id) AS retained
    FROM grid g
    JOIN cohorts c       ON c.cohort_month = g.cohort_month
    JOIN subscriptions s ON s.customer_id = c.customer_id
                        AND s.start_date <= g.month_end
                        AND (s.end_date IS NULL OR s.end_date > g.month_end)
    GROUP BY g.cohort_month, g.k
)
SELECT strftime('%Y-%m', g.cohort_month)                         AS cohort,
       g.cohort_size,
       g.k                                                       AS month_offset,
       COALESCE(r.retained, 0)                                   AS retained,
       ROUND(100.0 * COALESCE(r.retained, 0) / g.cohort_size, 1) AS retention_pct
FROM grid g
LEFT JOIN retained r ON r.cohort_month = g.cohort_month AND r.k = g.k
ORDER BY g.cohort_month, g.k;
