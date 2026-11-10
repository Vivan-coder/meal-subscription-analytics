-- 06 | Do bad deliveries in the first 28 days predict cancelling in days 28-90?
-- Design (to avoid reverse causation and censoring):
--   * only subscriptions that SURVIVED the first 28 days (so everyone had the
--     same 28-day window in which a bad delivery could happen),
--   * only subscriptions observable for 90 days,
--   * exposure  = number of late/failed deliveries in the first 28 days,
--   * outcome   = cancelled between day 28 and day 90.
-- Techniques: correlated subquery, CASE bucketing, observability filter.
WITH params AS (SELECT date(value, '+1 day') AS horizon FROM meta WHERE key = 'as_of_date'),
cohort AS (
    SELECT s.subscription_id, s.start_date, s.end_date,
           (SELECT COUNT(*) FROM orders o
            WHERE o.subscription_id = s.subscription_id
              AND o.delivery_status <> 'on_time'
              AND o.delivery_date < date(s.start_date, '+28 days')) AS bad_deliveries
    FROM subscriptions s, params p
    WHERE (s.end_date IS NULL OR s.end_date >= date(s.start_date, '+28 days'))
      AND date(s.start_date, '+90 days') <= p.horizon
)
SELECT CASE WHEN bad_deliveries = 0 THEN '0'
            WHEN bad_deliveries = 1 THEN '1'
            ELSE '2+' END                                              AS bad_deliveries_first_28d,
       COUNT(*)                                                        AS subscriptions,
       SUM(end_date IS NOT NULL AND end_date < date(start_date, '+90 days'))
                                                                       AS cancelled_day_28_to_90,
       ROUND(100.0 * SUM(end_date IS NOT NULL AND end_date < date(start_date, '+90 days'))
             / COUNT(*), 1)                                            AS cancel_rate_pct
FROM cohort
GROUP BY 1
ORDER BY 1;
