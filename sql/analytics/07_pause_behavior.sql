-- 07 | Is the fortnight after resuming from a pause risky?
-- Compares the cancellation rate in the 14 days after a pause ends with the
-- rate over all other at-risk time (both per 100 subscriber-months).
--   window exposure : pause_end .. min(pause_end + 14d, cancel date / horizon)
--   window event    : cancelled in (pause_end, pause_end + 14d]
-- Techniques: scalar MIN(a, b), exposure accounting, subtracting a subset from
-- the total to obtain the complementary group.
WITH params AS (SELECT date(value, '+1 day') AS horizon FROM meta WHERE key = 'as_of_date'),
post AS (
    SELECT p.pause_id,
           CAST(julianday(MIN(date(p.pause_end, '+14 days'), COALESCE(s.end_date, pr.horizon)))
                - julianday(p.pause_end) AS INTEGER)                AS window_days,
           (s.end_date IS NOT NULL
            AND s.end_date >  p.pause_end
            AND s.end_date <= date(p.pause_end, '+14 days'))        AS cancelled_in_window
    FROM subscription_pauses p
    JOIN subscriptions s ON s.subscription_id = p.subscription_id
    CROSS JOIN params pr
),
tot AS (
    SELECT SUM(e.exposure_days) AS exposure_days,
           SUM(s.end_date IS NOT NULL) AS cancellations
    FROM subscriptions s
    JOIN v_subscription_exposure e ON e.subscription_id = s.subscription_id
),
w AS (
    SELECT SUM(window_days) AS exposure_days, SUM(cancelled_in_window) AS cancellations FROM post
)
SELECT 'first 14 days after resuming a pause' AS period,
       w.cancellations,
       ROUND(w.exposure_days / 30.4375, 1)    AS subscriber_months,
       ROUND(100.0 * w.cancellations / (w.exposure_days / 30.4375), 2) AS churn_per_100_sub_months
FROM w
UNION ALL
SELECT 'all other at-risk time',
       tot.cancellations - w.cancellations,
       ROUND((tot.exposure_days - w.exposure_days) / 30.4375, 1),
       ROUND(100.0 * (tot.cancellations - w.cancellations)
             / ((tot.exposure_days - w.exposure_days) / 30.4375), 2)
FROM tot, w;
