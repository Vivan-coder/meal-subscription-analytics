-- 05 | Subscription survival
-- Of the subscriptions old enough to be observed for N full days, what share
-- lasted at least N days? Restricting to observable subscriptions removes the
-- censoring bias that a naive "currently active / total" ratio would have.
WITH params AS (SELECT date(value, '+1 day') AS horizon FROM meta WHERE key = 'as_of_date'),
milestones(days) AS (VALUES (7), (14), (30), (60), (90), (180), (270))
SELECT m.days                                                       AS days,
       COUNT(*)                                                     AS observable_subscriptions,
       SUM(s.end_date IS NULL
           OR julianday(s.end_date) - julianday(s.start_date) >= m.days) AS survivors,
       ROUND(100.0 * SUM(s.end_date IS NULL
           OR julianday(s.end_date) - julianday(s.start_date) >= m.days) / COUNT(*), 1)
                                                                    AS survival_pct
FROM milestones m
CROSS JOIN params p
JOIN subscriptions s ON date(s.start_date, '+' || m.days || ' days') <= p.horizon
GROUP BY m.days
ORDER BY m.days;
