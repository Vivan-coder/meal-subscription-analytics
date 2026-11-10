"""Shared fixtures. The databases are built once per test session."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from mealsub import recommend as R
from mealsub.db import connect, init_schema
from mealsub.generate import GenConfig, build_database

AS_OF = date(2025, 12, 31)


@pytest.fixture(scope="session")
def db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("analytics") / "test.db"
    build_database(path, GenConfig(n_customers=1000, seed=7))
    return path


@pytest.fixture(scope="session")
def db(db_path):
    """Medium database with recommendations persisted (read-only use)."""
    conn = connect(db_path)
    R.recommend_all(conn)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def small_db(tmp_path_factory):
    """Small database used to probe triggers (failed inserts leave no trace)."""
    path = tmp_path_factory.mktemp("small") / "small.db"
    build_database(path, GenConfig(n_customers=80, seed=3))
    conn = connect(path)
    yield conn
    conn.close()


@pytest.fixture()
def bare_db():
    """In-memory schema WITHOUT triggers: isolates CHECK / UNIQUE / FK constraints."""
    conn = connect(":memory:")
    init_schema(conn, triggers=False)
    conn.execute("INSERT INTO meta VALUES ('as_of_date', '2025-12-31')")
    conn.execute("INSERT INTO zones VALUES (1, 'Zone A')")
    conn.execute("INSERT INTO plans VALUES (1, 'Essentials', 2400)")
    conn.execute("INSERT INTO customers VALUES (1, 'Test User', 't@example.com', 1, '2025-01-01',"
                 " 'organic', 'maintain', 1500, 100)")
    conn.execute("INSERT INTO subscriptions VALUES (1, 1, 1, '2025-01-01', NULL, NULL)")
    yield conn
    conn.close()


# ----------------------------------------------------------------- helpers --
def parse(d: str | None) -> date | None:
    return date.fromisoformat(d) if d else None


def daterange(start: date, end: date):
    """Days d with start <= d < end."""
    d = start
    while d < end:
        yield d
        d += timedelta(days=1)


def load_subscriptions(conn):
    """List of dicts with parsed dates and the subscription's pauses."""
    pauses: dict = {}
    for r in conn.execute("SELECT subscription_id, pause_start, pause_end FROM subscription_pauses"):
        pauses.setdefault(r[0], []).append((parse(r[1]), parse(r[2])))
    subs = []
    for r in conn.execute("SELECT subscription_id, customer_id, plan_id, start_date, end_date, cancel_reason "
                          "FROM subscriptions ORDER BY subscription_id"):
        subs.append({"id": r[0], "customer": r[1], "plan": r[2], "start": parse(r[3]),
                     "end": parse(r[4]), "reason": r[5], "pauses": pauses.get(r[0], [])})
    return subs


def exposure_days(sub, horizon: date) -> int:
    end = sub["end"] or horizon
    return (end - sub["start"]).days - sum((pe - ps).days for ps, pe in sub["pauses"])
