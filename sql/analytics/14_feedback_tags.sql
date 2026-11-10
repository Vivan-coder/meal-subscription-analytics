-- 14 | What do customers say when they leave a tag?
-- Volume and average rating per feedback tag (untagged ratings excluded).
-- Techniques: window function for share, NULL-aware filtering.
SELECT feedback_tag                                         AS tag,
       COUNT(*)                                             AS mentions,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)   AS share_of_tagged_pct,
       ROUND(AVG(rating), 2)                                AS avg_rating
FROM meal_ratings
WHERE feedback_tag IS NOT NULL
GROUP BY feedback_tag
ORDER BY mentions DESC;
