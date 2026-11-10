"""Static reference data: allergens, ingredients, recipes, plans and delivery zones.

Meal nutrition is *not* stored anywhere. It is derived in SQL (``v_meal_nutrition``)
from ``meal_ingredients.grams`` x the per-100g values below, so the numbers are
internally consistent by construction.

Ingredient values are per 100 g (cooked/prepared where applicable) and rounded from
common USDA FoodData Central figures; they are realistic, not authoritative.
"""
from __future__ import annotations

ALLERGENS = [
    "gluten", "dairy", "eggs", "fish", "shellfish",
    "tree_nuts", "peanuts", "soy", "sesame",
]

# name, category, kcal, protein_g, carbs_g, fat_g, allergens   (all per 100 g)
INGREDIENTS = [
    # --- proteins -------------------------------------------------------
    ("chicken breast", "protein", 165, 31.0, 0.0, 3.6, []),
    ("chicken thigh", "protein", 209, 26.0, 0.0, 10.9, []),
    ("beef sirloin", "protein", 206, 27.0, 0.0, 10.0, []),
    ("ground beef", "protein", 250, 26.0, 0.0, 15.0, []),
    ("lamb", "protein", 250, 25.0, 0.0, 16.0, []),
    ("turkey breast", "protein", 135, 30.0, 0.0, 1.0, []),
    ("salmon", "protein", 208, 20.0, 0.0, 13.0, ["fish"]),
    ("cod", "protein", 105, 23.0, 0.0, 0.9, ["fish"]),
    ("tuna", "protein", 132, 28.0, 0.0, 1.3, ["fish"]),
    ("shrimp", "protein", 99, 24.0, 0.2, 0.3, ["shellfish"]),
    ("eggs", "protein", 143, 12.6, 0.7, 9.5, ["eggs"]),
    ("tofu", "protein", 144, 15.0, 3.0, 9.0, ["soy"]),
    ("chickpeas", "protein", 164, 8.9, 27.4, 2.6, []),
    ("lentils", "protein", 116, 9.0, 20.1, 0.4, []),
    ("black beans", "protein", 132, 8.9, 23.7, 0.5, []),
    ("edamame", "protein", 121, 11.9, 8.9, 5.2, ["soy"]),
    ("whey protein", "protein", 400, 80.0, 8.0, 6.0, ["dairy"]),
    # --- dairy ----------------------------------------------------------
    ("greek yogurt", "dairy", 59, 10.0, 3.6, 0.4, ["dairy"]),
    ("cottage cheese", "dairy", 98, 11.1, 3.4, 4.3, ["dairy"]),
    ("feta", "dairy", 264, 14.2, 4.1, 21.3, ["dairy"]),
    ("halloumi", "dairy", 321, 21.0, 2.2, 25.0, ["dairy"]),
    ("milk", "dairy", 61, 3.2, 4.8, 3.3, ["dairy"]),
    # --- carbs ----------------------------------------------------------
    ("brown rice", "carb", 123, 2.7, 25.6, 1.0, []),
    ("white rice", "carb", 130, 2.7, 28.2, 0.3, []),
    ("quinoa", "carb", 120, 4.4, 21.3, 1.9, []),
    ("sweet potato", "carb", 86, 1.6, 20.1, 0.1, []),
    ("potato", "carb", 77, 2.0, 17.5, 0.1, []),
    ("whole wheat pasta", "carb", 124, 5.3, 26.5, 0.5, ["gluten"]),
    ("whole wheat tortilla", "carb", 306, 8.0, 50.0, 8.0, ["gluten"]),
    ("oats", "carb", 389, 16.9, 66.3, 6.9, ["gluten"]),
    ("whole grain bread", "carb", 250, 12.0, 43.0, 4.0, ["gluten"]),
    ("couscous", "carb", 112, 3.8, 23.2, 0.2, ["gluten"]),
    ("bulgur", "carb", 83, 3.1, 18.6, 0.2, ["gluten"]),
    ("pita", "carb", 275, 9.1, 55.7, 1.2, ["gluten"]),
    ("granola", "carb", 471, 10.0, 64.0, 20.0, ["gluten", "tree_nuts"]),
    # --- fruit ----------------------------------------------------------
    ("banana", "fruit", 89, 1.1, 22.8, 0.3, []),
    ("berries", "fruit", 57, 0.7, 14.5, 0.3, []),
    ("apple", "fruit", 52, 0.3, 13.8, 0.2, []),
    ("dates", "fruit", 282, 2.5, 75.0, 0.4, []),
    # --- vegetables -----------------------------------------------------
    ("broccoli", "vegetable", 34, 2.8, 6.6, 0.4, []),
    ("spinach", "vegetable", 23, 2.9, 3.6, 0.4, []),
    ("zucchini", "vegetable", 17, 1.2, 3.1, 0.3, []),
    ("bell pepper", "vegetable", 31, 1.0, 6.0, 0.3, []),
    ("tomato", "vegetable", 18, 0.9, 3.9, 0.2, []),
    ("cucumber", "vegetable", 15, 0.7, 3.6, 0.1, []),
    ("carrot", "vegetable", 41, 0.9, 9.6, 0.2, []),
    ("eggplant", "vegetable", 25, 1.0, 5.9, 0.2, []),
    ("okra", "vegetable", 33, 1.9, 7.5, 0.2, []),
    ("cauliflower", "vegetable", 25, 1.9, 5.0, 0.3, []),
    ("mushrooms", "vegetable", 22, 3.1, 3.3, 0.3, []),
    ("green beans", "vegetable", 31, 1.8, 7.0, 0.2, []),
    ("mixed greens", "vegetable", 20, 1.8, 3.3, 0.3, []),
    # --- fats & other ---------------------------------------------------
    ("avocado", "fat", 160, 2.0, 8.5, 14.7, []),
    ("olive oil", "fat", 884, 0.0, 0.0, 100.0, []),
    ("tahini", "fat", 595, 17.0, 21.2, 53.8, ["sesame"]),
    ("almonds", "fat", 579, 21.2, 21.6, 49.9, ["tree_nuts"]),
    ("walnuts", "fat", 654, 15.2, 13.7, 65.2, ["tree_nuts"]),
    ("peanut butter", "fat", 588, 25.0, 20.0, 50.0, ["peanuts"]),
    ("chia seeds", "fat", 486, 16.5, 42.1, 30.7, []),
    ("hummus", "other", 166, 7.9, 14.3, 9.6, ["sesame"]),
    ("soy sauce", "other", 53, 8.1, 4.9, 0.6, ["soy", "gluten"]),
]

# name, cuisine, meal_type, [(ingredient, grams), ...]
MEALS = [
    # ===================== BREAKFAST (12) =====================
    ("Berry Greek Yogurt Parfait", "Mediterranean", "breakfast",
     [("greek yogurt", 200), ("berries", 100), ("granola", 30), ("chia seeds", 10)]),
    ("Veggie Egg Scramble", "American", "breakfast",
     [("eggs", 150), ("spinach", 50), ("mushrooms", 60), ("tomato", 50), ("olive oil", 8), ("whole grain bread", 50)]),
    ("Banana Almond Overnight Oats", "American", "breakfast",
     [("oats", 50), ("milk", 150), ("banana", 80), ("chia seeds", 10), ("almonds", 10)]),
    ("Shakshuka with Pita", "Middle Eastern", "breakfast",
     [("eggs", 150), ("tomato", 200), ("bell pepper", 60), ("olive oil", 8), ("pita", 60)]),
    ("Avocado Egg Toast", "American", "breakfast",
     [("whole grain bread", 80), ("avocado", 70), ("eggs", 100), ("tomato", 50)]),
    ("Spiced Chickpea Breakfast Bowl", "Middle Eastern", "breakfast",
     [("chickpeas", 150), ("tomato", 80), ("olive oil", 8), ("pita", 50), ("cucumber", 50)]),
    ("Oat Protein Pancakes", "American", "breakfast",
     [("oats", 50), ("eggs", 100), ("banana", 80), ("greek yogurt", 60), ("berries", 50)]),
    ("Cottage Cheese Berry Bowl", "Mediterranean", "breakfast",
     [("cottage cheese", 200), ("berries", 100), ("walnuts", 15), ("dates", 20)]),
    ("Black Bean Breakfast Burrito", "Mexican", "breakfast",
     [("whole wheat tortilla", 70), ("eggs", 90), ("black beans", 80), ("bell pepper", 50), ("avocado", 40)]),
    ("Salmon Cucumber Toast", "American", "breakfast",
     [("salmon", 60), ("whole grain bread", 70), ("cottage cheese", 60), ("cucumber", 40)]),
    ("Tofu Veggie Scramble", "Asian", "breakfast",
     [("tofu", 150), ("spinach", 50), ("mushrooms", 60), ("bell pepper", 50), ("olive oil", 8), ("whole grain bread", 50)]),
    ("Peanut Butter Banana Toast", "American", "breakfast",
     [("whole grain bread", 70), ("peanut butter", 20), ("banana", 100)]),
    # ===================== LUNCH (20) =====================
    ("Grilled Chicken Quinoa Bowl", "Mediterranean", "lunch",
     [("chicken breast", 150), ("quinoa", 180), ("cucumber", 60), ("tomato", 60), ("feta", 30), ("olive oil", 8)]),
    ("Chicken Shawarma Wrap", "Middle Eastern", "lunch",
     [("chicken thigh", 150), ("pita", 90), ("tomato", 50), ("cucumber", 50), ("hummus", 30)]),
    ("Beef Burrito Bowl", "Mexican", "lunch",
     [("ground beef", 120), ("white rice", 180), ("black beans", 80), ("avocado", 50), ("tomato", 50)]),
    ("Teriyaki Salmon Rice Bowl", "Asian", "lunch",
     [("salmon", 130), ("white rice", 180), ("broccoli", 100), ("soy sauce", 15)]),
    ("Chickpea Power Salad", "Mediterranean", "lunch",
     [("chickpeas", 150), ("mixed greens", 80), ("cucumber", 60), ("tomato", 60), ("feta", 30), ("olive oil", 12)]),
    ("Tuna Nicoise Salad", "Mediterranean", "lunch",
     [("tuna", 120), ("eggs", 100), ("green beans", 80), ("potato", 120), ("tomato", 60), ("olive oil", 10)]),
    ("Shrimp Tomato Pasta", "Italian", "lunch",
     [("shrimp", 130), ("whole wheat pasta", 200), ("tomato", 100), ("zucchini", 80), ("olive oil", 10)]),
    ("Turkey Avocado Sandwich", "American", "lunch",
     [("turkey breast", 120), ("whole grain bread", 100), ("avocado", 60), ("tomato", 50), ("mixed greens", 30)]),
    ("Lentil Soup with Bread", "Middle Eastern", "lunch",
     [("lentils", 250), ("carrot", 60), ("tomato", 80), ("olive oil", 10), ("whole grain bread", 80)]),
    ("Greek Chicken Salad", "Mediterranean", "lunch",
     [("chicken breast", 150), ("cucumber", 80), ("tomato", 80), ("feta", 40), ("olive oil", 10), ("mixed greens", 50)]),
    ("Beef and Broccoli Stir-fry", "Asian", "lunch",
     [("beef sirloin", 140), ("broccoli", 150), ("white rice", 180), ("soy sauce", 15), ("olive oil", 8)]),
    ("Tofu Veggie Stir-fry", "Asian", "lunch",
     [("tofu", 200), ("bell pepper", 80), ("broccoli", 100), ("brown rice", 200), ("soy sauce", 15), ("olive oil", 8)]),
    ("Halloumi Bulgur Bowl", "Mediterranean", "lunch",
     [("halloumi", 80), ("bulgur", 200), ("eggplant", 100), ("tomato", 80), ("olive oil", 5)]),
    ("Chicken Tikka with Basmati", "Indian", "lunch",
     [("chicken breast", 150), ("white rice", 180), ("greek yogurt", 50), ("tomato", 80), ("spinach", 50)]),
    ("Chana Masala", "Indian", "lunch",
     [("chickpeas", 250), ("tomato", 150), ("spinach", 60), ("olive oil", 10), ("white rice", 150)]),
    ("Turkey Meatball Pasta", "Italian", "lunch",
     [("turkey breast", 140), ("whole wheat pasta", 200), ("tomato", 150), ("spinach", 40)]),
    ("Salmon Poke Bowl", "Asian", "lunch",
     [("salmon", 120), ("white rice", 160), ("avocado", 50), ("cucumber", 60), ("edamame", 50), ("soy sauce", 12)]),
    ("Lamb Kofta Couscous Bowl", "Middle Eastern", "lunch",
     [("lamb", 130), ("couscous", 180), ("cucumber", 60), ("tomato", 60), ("tahini", 15)]),
    ("Black Bean Sweet Potato Bowl", "Mexican", "lunch",
     [("black beans", 200), ("sweet potato", 200), ("avocado", 60), ("bell pepper", 60)]),
    ("Egg Fried Rice with Vegetables", "Asian", "lunch",
     [("eggs", 150), ("white rice", 220), ("green beans", 60), ("carrot", 50), ("soy sauce", 15), ("olive oil", 10)]),
    # ===================== DINNER (20) =====================
    ("Herb Roasted Chicken with Sweet Potato", "American", "dinner",
     [("chicken thigh", 160), ("sweet potato", 200), ("broccoli", 120), ("olive oil", 10)]),
    ("Seared Salmon with Quinoa", "Mediterranean", "dinner",
     [("salmon", 150), ("quinoa", 150), ("green beans", 120), ("olive oil", 8)]),
    ("Sirloin Steak with Roasted Potatoes", "American", "dinner",
     [("beef sirloin", 160), ("potato", 200), ("cauliflower", 120), ("olive oil", 10)]),
    ("Garlic Shrimp with Brown Rice", "Mediterranean", "dinner",
     [("shrimp", 160), ("brown rice", 180), ("zucchini", 100), ("olive oil", 10)]),
    ("Creamy Chicken and Mushroom Pasta", "Italian", "dinner",
     [("chicken breast", 170), ("mushrooms", 120), ("greek yogurt", 80), ("whole wheat pasta", 150)]),
    ("Lamb and Okra Stew", "Middle Eastern", "dinner",
     [("lamb", 140), ("bulgur", 200), ("tomato", 100), ("okra", 100), ("olive oil", 8)]),
    ("Baked Cod with Potatoes", "Mediterranean", "dinner",
     [("cod", 200), ("potato", 220), ("spinach", 80), ("olive oil", 10)]),
    ("Turkey Chili", "Mexican", "dinner",
     [("turkey breast", 150), ("black beans", 150), ("tomato", 150), ("bell pepper", 60), ("white rice", 120)]),
    ("Okra Chickpea Tagine", "Middle Eastern", "dinner",
     [("chickpeas", 200), ("okra", 100), ("eggplant", 100), ("tomato", 150), ("olive oil", 12), ("white rice", 120)]),
    ("Tofu Cauliflower Curry", "Indian", "dinner",
     [("tofu", 200), ("cauliflower", 150), ("spinach", 60), ("tomato", 100), ("olive oil", 10), ("white rice", 150)]),
    ("Beef Tacos", "Mexican", "dinner",
     [("ground beef", 120), ("whole wheat tortilla", 100), ("tomato", 50), ("avocado", 50), ("greek yogurt", 40)]),
    ("Mediterranean Chicken with Feta", "Mediterranean", "dinner",
     [("chicken breast", 170), ("feta", 40), ("tomato", 120), ("zucchini", 100), ("couscous", 150)]),
    ("Teriyaki Chicken Stir-fry", "Asian", "dinner",
     [("chicken breast", 160), ("broccoli", 120), ("carrot", 60), ("white rice", 180), ("soy sauce", 15)]),
    ("Tuna Steak with Sweet Potato", "American", "dinner",
     [("tuna", 170), ("sweet potato", 220), ("green beans", 100), ("olive oil", 10)]),
    ("Spinach Mushroom Pasta Bake", "Italian", "dinner",
     [("whole wheat pasta", 220), ("spinach", 80), ("mushrooms", 100), ("cottage cheese", 100), ("tomato", 150), ("olive oil", 10)]),
    ("Beef Stuffed Bell Peppers", "Mediterranean", "dinner",
     [("ground beef", 130), ("bell pepper", 200), ("brown rice", 150), ("tomato", 80)]),
    ("Lemon Herb Turkey with Quinoa", "American", "dinner",
     [("turkey breast", 170), ("quinoa", 180), ("broccoli", 120), ("olive oil", 10)]),
    ("Miso-Style Salmon with Rice", "Asian", "dinner",
     [("salmon", 140), ("white rice", 180), ("edamame", 80), ("soy sauce", 15)]),
    ("Lentil Dal with Basmati", "Indian", "dinner",
     [("lentils", 300), ("tomato", 100), ("spinach", 60), ("olive oil", 12), ("white rice", 150)]),
    ("Lamb Souvlaki Plate", "Mediterranean", "dinner",
     [("lamb", 140), ("pita", 80), ("greek yogurt", 60), ("cucumber", 60), ("tomato", 60)]),
    # ===================== SNACK (12) =====================
    ("Hummus and Veggie Sticks", "Middle Eastern", "snack",
     [("hummus", 60), ("carrot", 80), ("cucumber", 80), ("bell pepper", 50)]),
    ("Apple with Almonds", "American", "snack",
     [("apple", 150), ("almonds", 20)]),
    ("Greek Yogurt with Berries", "Mediterranean", "snack",
     [("greek yogurt", 150), ("berries", 80)]),
    ("Banana Protein Shake", "American", "snack",
     [("whey protein", 30), ("milk", 200), ("banana", 50)]),
    ("Steamed Edamame", "Asian", "snack",
     [("edamame", 150)]),
    ("Boiled Eggs with Tomatoes", "Mediterranean", "snack",
     [("eggs", 100), ("tomato", 100)]),
    ("Tuna Cucumber Bites", "Mediterranean", "snack",
     [("tuna", 80), ("cucumber", 100), ("greek yogurt", 30)]),
    ("Almond Date Trail Mix", "Middle Eastern", "snack",
     [("almonds", 15), ("walnuts", 10), ("dates", 20)]),
    ("Cottage Cheese with Cucumber", "American", "snack",
     [("cottage cheese", 150), ("cucumber", 80)]),
    ("Crunchy Roasted Chickpeas", "Middle Eastern", "snack",
     [("chickpeas", 150), ("olive oil", 5)]),
    ("Turkey Hummus Roll-ups", "American", "snack",
     [("turkey breast", 80), ("cucumber", 50), ("hummus", 20)]),
    ("Peanut Butter Banana Bites", "American", "snack",
     [("banana", 100), ("peanut butter", 15), ("oats", 15)]),
]

# plan name, price per day (USD cents), slots served each delivery day
PLANS = [
    ("Essentials", 2400, ["lunch", "dinner"]),
    ("Balanced", 3200, ["breakfast", "lunch", "dinner"]),
    ("Complete", 3800, ["breakfast", "lunch", "dinner", "snack"]),
]

# Daily calorie-target range per plan (chosen so every plan can hit its target
# with the menu; verified by tests/test_catalog.py).
PLAN_CALORIE_RANGE = {
    "Essentials": (1100, 1400),
    "Balanced": (1400, 1700),
    "Complete": (1550, 1950),
}

# name, probability of a late delivery (failed ~ 1/5 of that). Zone F is the
# deliberately problematic zone the analytics should surface.
ZONES = [
    ("Zone A", 0.04), ("Zone B", 0.05), ("Zone C", 0.06),
    ("Zone D", 0.07), ("Zone E", 0.08), ("Zone F", 0.18),
]

CUISINES = sorted({m[1] for m in MEALS})

# Ingredients customers may list as dislikes.
DISLIKE_POOL = [
    "okra", "mushrooms", "eggplant", "tofu", "cauliflower", "avocado",
    "salmon", "tuna", "feta", "cottage cheese", "lentils", "spinach",
]

# Hidden "true taste" effects (rating points) planted in the synthetic data.
# The analytics must be able to recover these from ratings alone.
PLANTED_INGREDIENT_EFFECT = {
    "okra": -0.80, "tofu": -0.40, "eggplant": -0.30, "cauliflower": -0.20,
    "mushrooms": -0.15, "lentils": -0.10,
    "salmon": 0.40, "shrimp": 0.35, "halloumi": 0.35, "avocado": 0.20,
    "beef sirloin": 0.20, "chicken breast": 0.15,
}


def validate() -> None:
    """Raise AssertionError if the catalog is internally inconsistent."""
    ing_names = [i[0] for i in INGREDIENTS]
    assert len(ing_names) == len(set(ing_names)), "duplicate ingredient"
    known = set(ing_names)
    allergens = set(ALLERGENS)
    for name, cat, kcal, p, c, f, alls in INGREDIENTS:
        assert set(alls) <= allergens, f"unknown allergen on {name}"
        assert min(kcal, p, c, f) >= 0, name
    meal_names = [m[0] for m in MEALS]
    assert len(meal_names) == len(set(meal_names)), "duplicate meal"
    for name, cuisine, mtype, recipe in MEALS:
        assert mtype in {"breakfast", "lunch", "dinner", "snack"}, name
        used = [r[0] for r in recipe]
        assert len(used) == len(set(used)), f"repeated ingredient in {name}"
        assert set(used) <= known, f"unknown ingredient in {name}"
        assert all(g > 0 for _, g in recipe), name
    assert set(DISLIKE_POOL) <= known
    assert set(PLANTED_INGREDIENT_EFFECT) <= known
    assert set(PLAN_CALORIE_RANGE) == {p[0] for p in PLANS}


validate()
