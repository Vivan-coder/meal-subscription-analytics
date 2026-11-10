-- 10 | Meal leaderboard
-- Ranks every meal within its slot by the Bayesian-shrunk rating from
-- v_meal_rating (so a meal with 12 five-star ratings cannot outrank one with
-- 900 solid ratings). Also reports volume and rating coverage.
-- Techniques: RANK() OVER (PARTITION BY ...), view reuse, correlated count.
SELECT m.meal_type,
       RANK() OVER (PARTITION BY m.meal_type ORDER BY v.shrunk_rating DESC, m.meal_id) AS rank_in_slot,
       m.name,
       m.cuisine,
       (SELECT COUNT(*) FROM order_items oi WHERE oi.meal_id = m.meal_id) AS times_served,
       v.n_ratings,
       ROUND(v.avg_rating, 2)                                            AS avg_rating,
       ROUND(v.shrunk_rating, 3)                                         AS shrunk_rating,
       n.calories,
       n.protein_g
FROM meals m
JOIN v_meal_rating v    ON v.meal_id = m.meal_id
JOIN v_meal_nutrition n ON n.meal_id = m.meal_id
ORDER BY m.meal_type, rank_in_slot;
