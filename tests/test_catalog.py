"""Reference data is internally consistent and the menu can serve every plan."""
from __future__ import annotations

import itertools

from mealsub import catalog

ING = {i[0]: i for i in catalog.INGREDIENTS}
CALORIE_RANGE = {"breakfast": (300, 560), "lunch": (450, 760), "dinner": (450, 760), "snack": (110, 310)}


def _macros(recipe):
    k = sum(ING[i][2] * g / 100 for i, g in recipe)
    p = sum(ING[i][3] * g / 100 for i, g in recipe)
    c = sum(ING[i][4] * g / 100 for i, g in recipe)
    f = sum(ING[i][5] * g / 100 for i, g in recipe)
    return k, p, c, f


def test_catalog_validates():
    catalog.validate()


def test_menu_size_per_slot():
    counts = {t: sum(1 for m in catalog.MEALS if m[2] == t) for t in CALORIE_RANGE}
    assert counts == {"breakfast": 12, "lunch": 20, "dinner": 20, "snack": 12}


def test_calories_in_range_for_slot():
    for name, _c, mtype, recipe in catalog.MEALS:
        lo, hi = CALORIE_RANGE[mtype]
        kcal = _macros(recipe)[0]
        assert lo <= kcal <= hi, f"{name}: {kcal:.0f} kcal outside {lo}-{hi} for {mtype}"


def test_macros_are_consistent_with_calories():
    """Atwater (4/4/9) energy should be within 15% of the stated calories."""
    for name, _c, _t, recipe in catalog.MEALS:
        kcal, p, c, f = _macros(recipe)
        assert abs((4 * p + 4 * c + 9 * f) - kcal) / kcal < 0.15, name


def test_every_plan_can_reach_its_calorie_range():
    """For each plan some slot combination lands within +/-10% of both range ends."""
    by_type = {}
    for _n, _c, t, r in catalog.MEALS:
        by_type.setdefault(t, []).append(_macros(r)[0])
    for name, _price, slots in catalog.PLANS:
        lo, hi = catalog.PLAN_CALORIE_RANGE[name]
        sums = [sum(combo) for combo in itertools.product(*(by_type[s] for s in slots))]
        assert min(sums) <= lo * 1.10, f"{name}: menu cannot go low enough for {lo} kcal"
        assert max(sums) >= hi * 0.90, f"{name}: menu cannot go high enough for {hi} kcal"


def test_planted_effects_reference_used_ingredients():
    used = {i for m in catalog.MEALS for i, _g in m[3]}
    assert set(catalog.PLANTED_INGREDIENT_EFFECT) <= used


def test_sql_nutrition_view_matches_python(db):
    rows = {r["name"]: r for r in db.execute(
        "SELECT m.name, n.calories, n.protein_g, n.carbs_g, n.fat_g "
        "FROM meals m JOIN v_meal_nutrition n USING (meal_id)")}
    assert len(rows) == len(catalog.MEALS)
    for name, _c, _t, recipe in catalog.MEALS:
        k, p, c, f = _macros(recipe)
        r = rows[name]
        assert abs(r["calories"] - k) < 0.06 and abs(r["protein_g"] - p) < 0.06, name
        assert abs(r["carbs_g"] - c) < 0.06 and abs(r["fat_g"] - f) < 0.06, name
