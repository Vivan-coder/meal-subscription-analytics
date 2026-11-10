-- 11 | Which ingredients move ratings?
-- For each ingredient: mean rating of meals that contain it vs. meals that do
-- not, the difference ("lift"), and an approximate Welch z-score for it.
-- Only on-time deliveries are used, so late-delivery penalties cannot be
-- mistaken for a taste effect. Ingredients need >= 100 ratings on each side.
-- Techniques: multi-level CTE aggregation (sum, sum of squares) so a variance
-- can be derived without a self-join; SQRT.
WITH rated AS (
    SELECT oi.meal_id, mr.rating
    FROM meal_ratings mr
    JOIN order_items oi ON oi.order_item_id = mr.order_item_id
    JOIN orders o       ON o.order_id = oi.order_id
    WHERE o.delivery_status = 'on_time'
),
by_meal AS (
    SELECT meal_id, COUNT(*) AS n, SUM(rating) AS s, SUM(rating * rating) AS ss
    FROM rated GROUP BY meal_id
),
total AS (
    SELECT SUM(n) AS n, SUM(s) AS s, SUM(ss) AS ss FROM by_meal
),
by_ingredient AS (
    SELECT mi.ingredient_id, COUNT(*) AS meals_using,
           SUM(bm.n) AS n, SUM(bm.s) AS s, SUM(bm.ss) AS ss
    FROM by_meal bm
    JOIN meal_ingredients mi ON mi.meal_id = bm.meal_id
    GROUP BY mi.ingredient_id
),
stats AS (
    SELECT i.name, b.meals_using,
           b.n                                  AS n_with,
           t.n - b.n                            AS n_without,
           1.0 * b.s / b.n                      AS mean_with,
           1.0 * (t.s - b.s) / (t.n - b.n)      AS mean_without,
           1.0 * b.ss / b.n - (1.0 * b.s / b.n) * (1.0 * b.s / b.n)           AS var_with,
           1.0 * (t.ss - b.ss) / (t.n - b.n)
             - (1.0 * (t.s - b.s) / (t.n - b.n)) * (1.0 * (t.s - b.s) / (t.n - b.n)) AS var_without
    FROM by_ingredient b
    JOIN ingredients i ON i.ingredient_id = b.ingredient_id
    CROSS JOIN total t
    WHERE b.n >= 100 AND t.n - b.n >= 100
)
SELECT name                                     AS ingredient,
       meals_using,
       n_with                                   AS ratings_with,
       ROUND(mean_with, 3)                      AS avg_rating_with,
       ROUND(mean_without, 3)                   AS avg_rating_without,
       ROUND(mean_with - mean_without, 3)       AS lift,
       ROUND((mean_with - mean_without)
             / sqrt(var_with / n_with + var_without / n_without), 1) AS z_score
FROM stats
ORDER BY lift;
