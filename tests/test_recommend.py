"""Recommender: hard constraints never broken, plans deterministic and well-formed."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from mealsub import catalog
from mealsub import recommend as R
from mealsub.db import connect

MEAL_ALLERGENS = {}
_ing_all = {i[0]: set(i[6]) for i in catalog.INGREDIENTS}
for _n, _c, _t, _recipe in catalog.MEALS:
    MEAL_ALLERGENS[_n] = set().union(*(_ing_all[i] for i, _g in _recipe))
MEAL_INGREDIENTS = {m[0]: {i for i, _g in m[3]} for m in catalog.MEALS}


def test_sql_audit_reports_no_hard_violations(db):
    v = R.validate(db)
    hard = {k: n for k, n in v.items() if k not in ("planned_customer_days", "calorie_days_outside_tolerance")}
    assert hard == {k: 0 for k in hard} and len(hard) == 5
    assert v["planned_customer_days"] >= 5 * 400


def test_calorie_target_met_for_nearly_every_day(db):
    v = R.validate(db)
    assert v["calorie_days_outside_tolerance"] / v["planned_customer_days"] < 0.01


def test_every_active_customer_has_five_days(db):
    week = R.default_week(db).isoformat()
    n_active = len(R.active_customers(db))
    rows = db.execute("SELECT customer_id, COUNT(DISTINCT plan_date) FROM recommended_plans "
                      "WHERE plan_date >= ? GROUP BY customer_id", (week,)).fetchall()
    assert len(rows) == n_active
    assert all(r[1] == 5 for r in rows)


def test_independent_python_check_of_allergens_and_dislikes(db):
    allergens = {}
    for cid, name in db.execute("SELECT ca.customer_id, a.name FROM customer_allergens ca "
                                "JOIN allergens a USING (allergen_id)"):
        allergens.setdefault(cid, set()).add(name)
    dislikes = {}
    for cid, name in db.execute("SELECT cd.customer_id, i.name FROM customer_dislikes cd "
                                "JOIN ingredients i USING (ingredient_id)"):
        dislikes.setdefault(cid, set()).add(name)
    checked = 0
    for cid, meal in db.execute("SELECT rp.customer_id, m.name FROM recommended_plans rp "
                                "JOIN meals m USING (meal_id)"):
        assert not (MEAL_ALLERGENS[meal] & allergens.get(cid, set())), (cid, meal)
        assert not (MEAL_INGREDIENTS[meal] & dislikes.get(cid, set())), (cid, meal)
        checked += 1
    assert checked > 5000


def test_plan_structure_and_calories(db):
    cid = db.execute("SELECT customer_id FROM subscriptions WHERE end_date IS NULL "
                     "ORDER BY customer_id LIMIT 1").fetchone()[0]
    plan = R.plan_week(db, cid, R.default_week(db))
    _t, _p, _plan_id, slots = R.customer_context(db, cid)
    assert plan.unplanned_days == 0 and len(plan.days) == 5
    seen = set()
    for day in plan.days:
        assert set(day.meals) == set(slots)
        assert day.calories == pytest.approx(sum(m.calories for m in day.meals.values()), abs=0.11)
        if day.within_tolerance:
            assert abs(day.calories - plan.target_kcal) <= 0.10 * plan.target_kcal + 1e-9
        ids = {m.meal_id for m in day.meals.values()}
        assert not (ids & seen), "meal repeated within the week"
        seen |= ids
    assert [d.plan_date for d in plan.days] == [plan.week_start + timedelta(days=i) for i in range(5)]


def test_planning_is_deterministic(db):
    cid = R.active_customers(db)[3]
    week = R.default_week(db)
    a = R.plan_week(db, cid, week)
    b = R.plan_week(db, cid, week)
    assert [[m.meal_id for m in d.meals.values()] for d in a.days] == \
           [[m.meal_id for m in d.meals.values()] for d in b.days]


def test_tighter_tolerance_is_respected_or_flagged(db):
    cid = R.active_customers(db)[0]
    plan = R.plan_week(db, cid, R.default_week(db), tolerance=0.03)
    for day in plan.days:
        dev = abs(day.calories - plan.target_kcal) / plan.target_kcal
        assert (dev <= 0.03 + 1e-9) == day.within_tolerance


def test_week_start_must_be_a_monday(db):
    cid = R.active_customers(db)[0]
    with pytest.raises(ValueError, match="Monday"):
        R.plan_week(db, cid, date(2026, 1, 6))


def test_unknown_or_churned_customer_is_rejected(db):
    churned = db.execute("SELECT customer_id FROM customers WHERE customer_id NOT IN "
                         "(SELECT customer_id FROM subscriptions WHERE end_date IS NULL) LIMIT 1").fetchone()[0]
    with pytest.raises(ValueError, match="active subscription"):
        R.plan_week(db, churned, R.default_week(db))
    with pytest.raises(ValueError):
        R.plan_week(db, 10_000_000, R.default_week(db))


def test_default_week_is_the_first_monday_after_as_of(db):
    assert R.default_week(db) == date(2026, 1, 5)
    assert R.next_monday(date(2026, 1, 5)) == date(2026, 1, 12)     # strictly after
    assert R.next_monday(date(2026, 1, 4)) == date(2026, 1, 5)


def test_replanning_replaces_instead_of_duplicating(db_path):
    conn = connect(db_path)
    ids = R.active_customers(conn)[:5]
    R.recommend_all(conn, customers=ids)
    before = conn.execute("SELECT COUNT(*) FROM recommended_plans").fetchone()[0]
    R.recommend_all(conn, customers=ids)
    assert conn.execute("SELECT COUNT(*) FROM recommended_plans").fetchone()[0] == before
    conn.close()
