"""Constraints (CHECK/UNIQUE/FK) and temporal-integrity triggers reject bad data."""
from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from conftest import parse


def raises(conn, sql, params=(), match=None):
    with pytest.raises(sqlite3.IntegrityError) as exc:
        conn.execute(sql, params)
    if match:
        assert match in str(exc.value)


# ---------------------------------------------------------------- constraints --
def test_failed_orders_must_be_free_and_paid_orders_must_not(bare_db):
    raises(bare_db, "INSERT INTO orders VALUES (1, 1, '2025-01-06', 'failed', 2400)")
    raises(bare_db, "INSERT INTO orders VALUES (1, 1, '2025-01-06', 'on_time', 0)")
    bare_db.execute("INSERT INTO orders VALUES (1, 1, '2025-01-06', 'failed', 0)")
    bare_db.execute("INSERT INTO orders VALUES (2, 1, '2025-01-07', 'late', 2400)")


def test_weekend_orders_rejected(bare_db):
    raises(bare_db, "INSERT INTO orders VALUES (1, 1, '2025-01-04', 'on_time', 2400)")  # Saturday
    raises(bare_db, "INSERT INTO orders VALUES (1, 1, '2025-01-05', 'on_time', 2400)")  # Sunday
    bare_db.execute("INSERT INTO orders VALUES (1, 1, '2025-01-06', 'on_time', 2400)")  # Monday


def test_one_order_per_subscription_per_day(bare_db):
    bare_db.execute("INSERT INTO orders VALUES (1, 1, '2025-01-06', 'on_time', 2400)")
    raises(bare_db, "INSERT INTO orders VALUES (2, 1, '2025-01-06', 'on_time', 2400)")


def test_invalid_dates_rejected(bare_db):
    raises(bare_db, "INSERT INTO orders VALUES (1, 1, '2025-02-30', 'on_time', 2400)")
    raises(bare_db, "INSERT INTO orders VALUES (1, 1, '06/01/2025', 'on_time', 2400)")


def test_subscription_end_must_follow_start_and_match_reason(bare_db):
    raises(bare_db, "INSERT INTO subscriptions VALUES (2, 1, 1, '2025-03-01', '2025-03-01', 'price')")
    raises(bare_db, "INSERT INTO subscriptions VALUES (2, 1, 1, '2025-03-01', '2025-02-01', 'price')")
    raises(bare_db, "INSERT INTO subscriptions VALUES (2, 1, 1, '2025-03-01', '2025-04-01', NULL)")
    raises(bare_db, "INSERT INTO subscriptions VALUES (2, 1, 1, '2025-03-01', NULL, 'price')")
    raises(bare_db, "INSERT INTO subscriptions VALUES (2, 1, 1, '2025-03-01', '2025-04-01', 'bogus')")
    bare_db.execute("INSERT INTO subscriptions VALUES (2, 1, 1, '2025-03-01', '2025-04-01', 'price')")


def test_value_constraints(bare_db):
    raises(bare_db, "INSERT INTO plans VALUES (2, 'Free', 0)")
    raises(bare_db, "INSERT INTO plans VALUES (2, 'Neg', -5)")
    raises(bare_db, "INSERT INTO meals VALUES (1, 'x', 'y', 'brunch')")
    raises(bare_db, "INSERT INTO ingredients VALUES (1, 'x', 'protein', -1, 0, 0, 0)")
    raises(bare_db, "INSERT INTO customers VALUES (2, 'A', 'a@example.com', 1, '2025-01-01',"
                    " 'tv', 'maintain', 1500, 100)")
    raises(bare_db, "INSERT INTO customers VALUES (2, 'A', 't@example.com', 1, '2025-01-01',"
                    " 'organic', 'maintain', 1500, 100)")        # duplicate email
    raises(bare_db, "INSERT INTO customers VALUES (2, 'A', 'a@example.com', 1, '2025-01-01',"
                    " 'organic', 'maintain', 200, 100)")         # calories below 1000


def test_foreign_keys_enforced(bare_db):
    raises(bare_db, "INSERT INTO subscriptions VALUES (9, 999, 1, '2025-01-01', NULL, NULL)")
    raises(bare_db, "INSERT INTO orders VALUES (1, 999, '2025-01-06', 'on_time', 2400)")


def test_rating_range(bare_db):
    bare_db.execute("INSERT INTO meals VALUES (1, 'm', 'c', 'lunch')")
    bare_db.execute("INSERT INTO orders VALUES (1, 1, '2025-01-06', 'on_time', 2400)")
    bare_db.execute("INSERT INTO order_items VALUES (1, 1, 1)")
    raises(bare_db, "INSERT INTO meal_ratings VALUES (1, 6, NULL, '2025-01-07')")
    raises(bare_db, "INSERT INTO meal_ratings VALUES (1, 0, NULL, '2025-01-07')")
    raises(bare_db, "INSERT INTO meal_ratings VALUES (1, 4, 'weird', '2025-01-07')")
    bare_db.execute("INSERT INTO meal_ratings VALUES (1, 4, 'delicious', '2025-01-07')")


# ------------------------------------------------------------------- triggers --
def _first(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    assert row is not None, "fixture data lacks a row needed by this test"
    return row


def _weekday_on_or_after(d):
    while d.weekday() > 4:
        d += timedelta(days=1)
    return d


def test_trigger_order_after_cancellation(small_db):
    sub = _first(small_db, "SELECT subscription_id, end_date FROM subscriptions "
                           "WHERE end_date IS NOT NULL LIMIT 1")
    day = _weekday_on_or_after(parse(sub["end_date"]))          # first day after the window
    raises(small_db, "INSERT INTO orders (subscription_id, delivery_date, delivery_status, amount_cents) "
                     "VALUES (?, ?, 'on_time', 2400)", (sub["subscription_id"], day.isoformat()),
           "outside subscription window")


def test_trigger_order_before_start(small_db):
    sub = _first(small_db, "SELECT subscription_id, start_date FROM subscriptions LIMIT 1")
    d = parse(sub["start_date"]) - timedelta(days=7)
    d = d - timedelta(days=max(0, d.weekday() - 4))
    raises(small_db, "INSERT INTO orders (subscription_id, delivery_date, delivery_status, amount_cents) "
                     "VALUES (?, ?, 'on_time', 2400)", (sub["subscription_id"], d.isoformat()),
           "outside subscription window")


def test_trigger_order_after_as_of(small_db):
    sub = _first(small_db, "SELECT subscription_id FROM subscriptions WHERE end_date IS NULL LIMIT 1")
    raises(small_db, "INSERT INTO orders (subscription_id, delivery_date, delivery_status, amount_cents) "
                     "VALUES (?, '2026-01-05', 'on_time', 2400)", (sub["subscription_id"],),
           "outside subscription window")


def test_trigger_order_inside_pause(small_db):
    p = _first(small_db, "SELECT subscription_id, pause_start, pause_end FROM subscription_pauses LIMIT 1")
    day = _weekday_on_or_after(parse(p["pause_start"]))
    assert day < parse(p["pause_end"])
    raises(small_db, "INSERT INTO orders (subscription_id, delivery_date, delivery_status, amount_cents) "
                     "VALUES (?, ?, 'on_time', 2400)", (p["subscription_id"], day.isoformat()),
           "inside a pause")


def test_trigger_overlapping_pause(small_db):
    p = _first(small_db, "SELECT subscription_id, pause_start FROM subscription_pauses LIMIT 1")
    inside = parse(p["pause_start"]) + timedelta(days=1)
    raises(small_db, "INSERT INTO subscription_pauses (subscription_id, pause_start, pause_end) VALUES (?,?,?)",
           (p["subscription_id"], inside.isoformat(), (inside + timedelta(days=2)).isoformat()),
           "overlapping pause")


def test_trigger_pause_outside_subscription(small_db):
    sub = _first(small_db, "SELECT subscription_id, start_date FROM subscriptions LIMIT 1")
    start = parse(sub["start_date"]) - timedelta(days=20)
    raises(small_db, "INSERT INTO subscription_pauses (subscription_id, pause_start, pause_end) VALUES (?,?,?)",
           (sub["subscription_id"], start.isoformat(), (start + timedelta(days=7)).isoformat()),
           "outside subscription window")


def test_trigger_item_for_slot_not_in_plan(small_db):
    row = _first(small_db, """
        SELECT o.order_id, (SELECT meal_id FROM meals WHERE meal_type = 'snack' LIMIT 1) AS snack
        FROM orders o JOIN subscriptions s ON s.subscription_id = o.subscription_id
        WHERE s.plan_id = 1 LIMIT 1""")                           # Essentials: lunch + dinner only
    raises(small_db, "INSERT INTO order_items (order_id, meal_id) VALUES (?, ?)",
           (row["order_id"], row["snack"]), "not part of the subscription plan")


def test_trigger_second_meal_in_same_slot(small_db):
    row = _first(small_db, """
        SELECT oi.order_id, m.meal_type FROM order_items oi JOIN meals m ON m.meal_id = oi.meal_id LIMIT 1""")
    other = _first(small_db, """
        SELECT meal_id FROM meals WHERE meal_type = ?
          AND meal_id NOT IN (SELECT meal_id FROM order_items WHERE order_id = ?) LIMIT 1""",
                   (row["meal_type"], row["order_id"]))
    raises(small_db, "INSERT INTO order_items (order_id, meal_id) VALUES (?, ?)",
           (row["order_id"], other["meal_id"]), "already has a meal for this slot")


def test_trigger_rating_on_failed_delivery(small_db):
    row = _first(small_db, """
        SELECT oi.order_item_id, o.delivery_date FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id WHERE o.delivery_status = 'failed' LIMIT 1""")
    raises(small_db, "INSERT INTO meal_ratings VALUES (?, 3, NULL, ?)",
           (row["order_item_id"], row["delivery_date"]), "undelivered")


def test_trigger_rating_before_delivery_and_after_as_of(small_db):
    row = _first(small_db, """
        SELECT oi.order_item_id, o.delivery_date FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        WHERE o.delivery_status = 'on_time'
          AND oi.order_item_id NOT IN (SELECT order_item_id FROM meal_ratings) LIMIT 1""")
    before = (parse(row["delivery_date"]) - timedelta(days=1)).isoformat()
    raises(small_db, "INSERT INTO meal_ratings VALUES (?, 3, NULL, ?)", (row["order_item_id"], before),
           "before delivery")
    raises(small_db, "INSERT INTO meal_ratings VALUES (?, 3, NULL, '2026-02-01')", (row["order_item_id"],),
           "after the dataset")


def test_valid_inserts_still_work_inside_a_rolled_back_transaction(small_db):
    """Guards against triggers that reject everything."""
    row = _first(small_db, """
        SELECT oi.order_item_id, o.delivery_date FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        WHERE o.delivery_status = 'on_time'
          AND oi.order_item_id NOT IN (SELECT order_item_id FROM meal_ratings) LIMIT 1""")
    small_db.execute("SAVEPOINT t")
    try:
        small_db.execute("INSERT INTO meal_ratings VALUES (?, 5, 'delicious', ?)",
                         (row["order_item_id"], row["delivery_date"]))
    finally:
        small_db.execute("ROLLBACK TO t")
        small_db.execute("RELEASE t")
