"""Properties of the generated database, checked independently of the SQL audit."""
from __future__ import annotations

from datetime import date, timedelta

from conftest import AS_OF, daterange, load_subscriptions, parse
from mealsub.db import connect, verify
from mealsub.generate import GenConfig, build_database


def test_integrity_audit_is_clean(db):
    results = verify(db)
    assert len(results) >= 14
    assert [(n, v) for n, v in results if v] == []


def test_sqlite_integrity_and_foreign_keys(db):
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_every_eligible_delivery_day_has_exactly_one_order(db):
    """Independent of SQL: expected weekdays per subscription == orders present."""
    horizon = AS_OF + timedelta(days=1)
    actual = {r[0]: {parse(x) for x in r[1].split(",")}
              for r in db.execute("SELECT subscription_id, group_concat(delivery_date) "
                                  "FROM orders GROUP BY subscription_id")}
    for sub in load_subscriptions(db):
        paused = {d for ps, pe in sub["pauses"] for d in daterange(ps, pe)}
        expected = {d for d in daterange(sub["start"], min(sub["end"] or horizon, horizon))
                    if d.weekday() < 5 and d not in paused}
        assert actual.get(sub["id"], set()) == expected, f"subscription {sub['id']}"


def test_dataset_has_expected_shape(db):
    assert db.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 1000
    assert db.execute("SELECT COUNT(*) FROM meals").fetchone()[0] == 64
    assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] > 50_000
    assert db.execute("SELECT MAX(delivery_date) FROM orders").fetchone()[0] <= AS_OF.isoformat()
    assert db.execute("SELECT COUNT(*) FROM subscription_pauses").fetchone()[0] > 100


def test_each_customer_has_enough_menu_choice(db):
    """Every customer keeps >= 7 eligible meals per slot, so weekly plans are feasible."""
    rows = db.execute("""
        SELECT c.customer_id, ps.meal_type, COUNT(*) AS n
        FROM customers c
        JOIN subscriptions s ON s.customer_id = c.customer_id
        JOIN plan_slots ps   ON ps.plan_id = s.plan_id
        JOIN meals m         ON m.meal_type = ps.meal_type
        WHERE NOT EXISTS (SELECT 1 FROM v_meal_allergens ma JOIN customer_allergens ca
                          ON ca.allergen_id = ma.allergen_id
                          WHERE ma.meal_id = m.meal_id AND ca.customer_id = c.customer_id)
          AND NOT EXISTS (SELECT 1 FROM meal_ingredients mi JOIN customer_dislikes cd
                          ON cd.ingredient_id = mi.ingredient_id
                          WHERE mi.meal_id = m.meal_id AND cd.customer_id = c.customer_id)
        GROUP BY c.customer_id, ps.meal_type""").fetchall()
    assert rows and min(r["n"] for r in rows) >= 7


def test_build_is_deterministic(tmp_path):
    def fingerprint(path):
        conn = connect(path)
        out = [conn.execute(f"SELECT {agg} FROM {t}").fetchone()[0] for t, agg in (
            ("orders", "group_concat(order_id || delivery_date || delivery_status, '|')"),
            ("meal_ratings", "group_concat(order_item_id || ':' || rating, '|')"),
            ("subscriptions", "group_concat(subscription_id || coalesce(end_date, '-'), '|')"))]
        conn.close()
        return out

    a, b, c = tmp_path / "a.db", tmp_path / "b.db", tmp_path / "c.db"
    build_database(a, GenConfig(n_customers=40, seed=5))
    build_database(b, GenConfig(n_customers=40, seed=5))
    build_database(c, GenConfig(n_customers=40, seed=6))
    assert fingerprint(a) == fingerprint(b)
    assert fingerprint(a) != fingerprint(c)


def test_resubscriptions_are_sequential(db):
    by_customer: dict = {}
    for s in load_subscriptions(db):
        by_customer.setdefault(s["customer"], []).append(s)
    multi = [v for v in by_customer.values() if len(v) > 1]
    assert multi, "expected some win-back customers"
    for subs in multi:
        subs.sort(key=lambda s: s["start"])
        for prev, nxt in zip(subs, subs[1:]):
            assert prev["end"] is not None and nxt["start"] >= prev["end"] + timedelta(days=30)
