-- 03 | Churn rate by segment (exposure-adjusted)
-- churn_per_100_sub_months = 100 x cancellations / subscriber-months at risk.
-- Dividing by *exposure* (not by head-count) keeps young and old segments
-- comparable and avoids survivorship bias. Paused days are not at-risk time.
-- Techniques: UNION ALL of dimensions over one CTE, derived exposure view.
WITH base AS (
    SELECT s.subscription_id,
           (s.end_date IS NOT NULL)  AS churned,
           e.exposure_days,
           c.acquisition_channel     AS channel,
           z.name                    AS zone,
           p.name                    AS plan,
           c.goal                    AS goal
    FROM subscriptions s
    JOIN v_subscription_exposure e ON e.subscription_id = s.subscription_id
    JOIN customers c ON c.customer_id = s.customer_id
    JOIN zones z     ON z.zone_id = c.zone_id
    JOIN plans p     ON p.plan_id = s.plan_id
),
long AS (
    SELECT 'acquisition_channel' AS dimension, channel AS segment, churned, exposure_days FROM base
    UNION ALL SELECT 'delivery_zone', zone, churned, exposure_days FROM base
    UNION ALL SELECT 'plan', plan, churned, exposure_days FROM base
    UNION ALL SELECT 'goal', goal, churned, exposure_days FROM base
)
SELECT dimension,
       segment,
       COUNT(*)                                              AS subscriptions,
       SUM(churned)                                          AS cancellations,
       ROUND(SUM(exposure_days) / 30.4375, 0)                AS subscriber_months,
       ROUND(100.0 * SUM(churned) / (SUM(exposure_days) / 30.4375), 2)
                                                             AS churn_per_100_sub_months
FROM long
GROUP BY dimension, segment
ORDER BY dimension, churn_per_100_sub_months DESC;
