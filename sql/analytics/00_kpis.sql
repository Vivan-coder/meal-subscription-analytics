-- 00 | Headline KPIs (single row)
SELECT (SELECT COUNT(*) FROM customers)                                         AS customers,
       (SELECT COUNT(*) FROM subscriptions WHERE end_date IS NULL)              AS active_subscriptions,
       (SELECT COUNT(*) FROM orders)                                            AS orders,
       (SELECT ROUND(SUM(amount_cents) / 100.0, 0) FROM orders)                 AS total_revenue_usd,
       (SELECT ROUND(100.0 * SUM(delivery_status = 'on_time') / COUNT(*), 1)
        FROM orders)                                                            AS on_time_pct,
       (SELECT COUNT(*) FROM meal_ratings)                                      AS ratings,
       (SELECT ROUND(AVG(rating), 2) FROM meal_ratings)                         AS avg_rating,
       (SELECT MIN(delivery_date) FROM orders)                                  AS first_order,
       (SELECT value FROM meta WHERE key = 'as_of_date')                        AS as_of;
