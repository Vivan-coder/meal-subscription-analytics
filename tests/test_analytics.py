"""Every important SQL metric is recomputed in plain Python from the raw tables and compared."""
from __future__ import annotations

import calendar
import math
from collections import defaultdict
from datetime import date, timedelta

import pytest

from conftest import AS_OF, exposure_days, load_subscriptions, parse
from mealsub.db import analytics, list_analytics

HORIZON = AS_OF + timedelta(days=1)


def month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def add_months(y: int, m: int, k: int):
    idx = y * 12 + (m - 1) + k
    return idx // 12, idx % 12 + 1


@pytest.mark.parametrize("name", list_analytics())
def test_every_query_runs_and_returns_rows(db, name):
    assert len(analytics(db, name)) > 0


# ---------------------------------------------------------------- 01 revenue --
def test_monthly_revenue_matches_python(db):
    rows = analytics(db, "01_monthly_revenue")
    expected = defaultdict(lambda: [0, 0])
    for d, amt in db.execute("SELECT delivery_date, amount_cents FROM orders"):
        e = expected[d[:7]]
        e[0] += amt
        e[1] += 1
    assert {r["month"] for r in rows} >= set(expected)
    for r in rows:
        rev, n = expected.get(r["month"], [0, 0])
        assert r["revenue_usd"] == pytest.approx(rev / 100, abs=0.005)
        assert r["orders"] == n
    total = sum(r["revenue_usd"] for r in rows)
    assert total == pytest.approx(db.execute("SELECT SUM(amount_cents) FROM orders").fetchone()[0] / 100, abs=0.5)


def test_active_subscribers_and_flows_match_python(db):
    subs = load_subscriptions(db)
    first_start = {}
    for s in subs:
        first_start[s["customer"]] = min(first_start.get(s["customer"], s["start"]), s["start"])
    for r in analytics(db, "01_monthly_revenue"):
        y, m = map(int, r["month"].split("-"))
        me = min(month_end(y, m), AS_OF)
        assert r["active_subscribers"] == sum(
            1 for s in subs if s["start"] <= me and (s["end"] is None or s["end"] > me))
        assert r["new_customers"] == sum(1 for d in first_start.values() if (d.year, d.month) == (y, m))
        assert r["cancellations"] == sum(1 for s in subs if s["end"] and (s["end"].year, s["end"].month) == (y, m))
        assert r["reactivations"] == sum(1 for s in subs if (s["start"].year, s["start"].month) == (y, m)
                                         and s["start"] > first_start[s["customer"]])


def test_mom_growth_is_consistent(db):
    rows = analytics(db, "01_monthly_revenue")
    assert rows[0]["mom_growth_pct"] is None
    for prev, cur in zip(rows, rows[1:]):
        assert cur["mom_growth_pct"] == pytest.approx(
            100 * (cur["revenue_usd"] - prev["revenue_usd"]) / prev["revenue_usd"], abs=0.06)


# ---------------------------------------------------------------- 02 cohorts --
def test_cohort_retention_matches_python(db):
    subs = load_subscriptions(db)
    first = {}
    for s in subs:
        first[s["customer"]] = min(first.get(s["customer"], s["start"]), s["start"])
    cohorts = defaultdict(list)
    for cust, d in first.items():
        cohorts[(d.year, d.month)].append(cust)
    by_customer = defaultdict(list)
    for s in subs:
        by_customer[s["customer"]].append(s)

    expected = {}
    for (y, m), custs in cohorts.items():
        for k in range(0, 37):
            yy, mm = add_months(y, m, k)
            me = month_end(yy, mm)
            if me > AS_OF:
                break
            retained = sum(1 for c in custs if any(
                s["start"] <= me and (s["end"] is None or s["end"] > me) for s in by_customer[c]))
            expected[(f"{y:04d}-{m:02d}", k)] = (len(custs), retained)

    rows = analytics(db, "02_cohort_retention")
    got = {(r["cohort"], r["month_offset"]): (r["cohort_size"], r["retained"]) for r in rows}
    assert got == expected
    for r in rows:
        assert r["retention_pct"] == pytest.approx(100 * r["retained"] / r["cohort_size"], abs=0.06)


def test_retention_never_exceeds_100_and_month0_is_high(db):
    rows = analytics(db, "02_cohort_retention")
    assert all(0 <= r["retention_pct"] <= 100 for r in rows)
    m0 = [r["retention_pct"] for r in rows if r["month_offset"] == 0]
    assert min(m0) > 85


# -------------------------------------------------------------------- 03 churn --
def test_churn_by_segment_matches_python(db):
    subs = load_subscriptions(db)
    cust = {r[0]: r for r in db.execute(
        "SELECT c.customer_id, c.acquisition_channel, z.name, c.goal "
        "FROM customers c JOIN zones z USING (zone_id)")}
    plan_name = {r[0]: r[1] for r in db.execute("SELECT plan_id, name FROM plans")}
    agg = defaultdict(lambda: [0, 0, 0])      # subs, cancellations, exposure days
    for s in subs:
        c = cust[s["customer"]]
        for dim, seg in (("acquisition_channel", c[1]), ("delivery_zone", c[2]),
                         ("goal", c[3]), ("plan", plan_name[s["plan"]])):
            a = agg[(dim, seg)]
            a[0] += 1
            a[1] += s["end"] is not None
            a[2] += exposure_days(s, HORIZON)
    rows = analytics(db, "03_churn_by_segment")
    assert len(rows) == len(agg)
    for r in rows:
        n, canc, exp = agg[(r["dimension"], r["segment"])]
        assert (r["subscriptions"], r["cancellations"]) == (n, canc)
        assert r["churn_per_100_sub_months"] == pytest.approx(100 * canc / (exp / 30.4375), abs=0.006)


def test_cancellation_reasons_match_python(db):
    subs = [s for s in load_subscriptions(db) if s["end"]]
    rows = analytics(db, "04_cancellation_reasons")
    assert sum(r["cancellations"] for r in rows) == len(subs)
    assert sum(r["share_pct"] for r in rows) == pytest.approx(100, abs=0.5)
    for r in rows:
        mine = [s for s in subs if s["reason"] == r["reason"]]
        assert r["cancellations"] == len(mine)
        assert r["avg_days_subscribed"] == pytest.approx(
            sum((s["end"] - s["start"]).days for s in mine) / len(mine), abs=0.06)
        assert r["cancelled_within_30d_pct"] == pytest.approx(
            100 * sum((s["end"] - s["start"]).days <= 30 for s in mine) / len(mine), abs=0.06)


def test_survival_matches_python_and_is_monotone(db):
    subs = load_subscriptions(db)
    rows = analytics(db, "05_survival_curve")
    for r in rows:
        n = r["days"]
        obs = [s for s in subs if s["start"] + timedelta(days=n) <= HORIZON]
        surv = [s for s in obs if s["end"] is None or (s["end"] - s["start"]).days >= n]
        assert (r["observable_subscriptions"], r["survivors"]) == (len(obs), len(surv))
    pct = [r["survival_pct"] for r in rows]
    assert pct == sorted(pct, reverse=True)


# --------------------------------------------------------- 06 / 07 behaviour --
def test_delivery_vs_churn_matches_python(db):
    subs = load_subscriptions(db)
    bad = defaultdict(list)
    for sid, d in db.execute("SELECT subscription_id, delivery_date FROM orders "
                             "WHERE delivery_status <> 'on_time'"):
        bad[sid].append(parse(d))
    buckets = defaultdict(lambda: [0, 0])
    for s in subs:
        d28, d90 = s["start"] + timedelta(days=28), s["start"] + timedelta(days=90)
        if (s["end"] is not None and s["end"] < d28) or d90 > HORIZON:
            continue
        n_bad = sum(1 for d in bad[s["id"]] if d < d28)
        key = "0" if n_bad == 0 else "1" if n_bad == 1 else "2+"
        buckets[key][0] += 1
        buckets[key][1] += s["end"] is not None and s["end"] < d90
    rows = analytics(db, "06_delivery_vs_churn")
    assert {r["bad_deliveries_first_28d"]: [r["subscriptions"], r["cancelled_day_28_to_90"]]
            for r in rows} == dict(buckets)


def test_pause_behavior_matches_python(db):
    subs = load_subscriptions(db)
    w_exp = w_cancel = 0
    for s in subs:
        for _ps, pe in s["pauses"]:
            w_exp += (min(pe + timedelta(days=14), s["end"] or HORIZON) - pe).days
            w_cancel += s["end"] is not None and pe < s["end"] <= pe + timedelta(days=14)
    tot_exp = sum(exposure_days(s, HORIZON) for s in subs)
    tot_cancel = sum(s["end"] is not None for s in subs)
    rows = {r["period"]: r for r in analytics(db, "07_pause_behavior")}
    w = rows["first 14 days after resuming a pause"]
    o = rows["all other at-risk time"]
    assert w["cancellations"] == w_cancel and o["cancellations"] == tot_cancel - w_cancel
    assert w["churn_per_100_sub_months"] == pytest.approx(100 * w_cancel / (w_exp / 30.4375), abs=0.006)
    assert o["churn_per_100_sub_months"] == pytest.approx(
        100 * (tot_cancel - w_cancel) / ((tot_exp - w_exp) / 30.4375), abs=0.006)


# ------------------------------------------------------------- 08 / 09 value --
def test_customer_value_matches_python(db):
    revenue = defaultdict(int)
    for cid, amt in db.execute("SELECT s.customer_id, o.amount_cents FROM orders o "
                               "JOIN subscriptions s USING (subscription_id)"):
        revenue[cid] += amt
    channel = {r[0]: r[1] for r in db.execute("SELECT customer_id, acquisition_channel FROM customers")}
    groups = defaultdict(list)
    for cid, ch in channel.items():
        groups[ch].append(revenue[cid])
    rows = analytics(db, "08_customer_value")
    assert sum(r["customers"] for r in rows) == len(channel)
    for r in rows:
        v = groups[r["channel"]]
        assert r["customers"] == len(v)
        assert r["avg_ltv_to_date_usd"] == pytest.approx(sum(v) / len(v) / 100, abs=0.006)
    assert sum(r["total_revenue_usd"] for r in rows) == pytest.approx(sum(revenue.values()) / 100, abs=len(rows))


def test_revenue_concentration(db):
    rows = analytics(db, "09_revenue_concentration")
    assert [r["decile"] for r in rows] == list(range(1, 11))
    assert sum(r["customers"] for r in rows) >= 900
    assert sum(r["share_pct"] for r in rows) == pytest.approx(100, abs=0.6)
    assert rows[-1]["cumulative_share_pct"] == pytest.approx(100, abs=0.01)
    shares = [r["share_pct"] for r in rows]
    assert shares == sorted(shares, reverse=True)
    assert rows[0]["min_customer_usd"] >= rows[1]["max_customer_usd"] - 1


# ---------------------------------------------------------------- feedback --
def test_meal_leaderboard_matches_python(db):
    rows = analytics(db, "10_meal_ratings")
    assert len(rows) == 64
    all_ratings = [r[0] for r in db.execute("SELECT rating FROM meal_ratings")]
    mu = sum(all_ratings) / len(all_ratings)
    per_meal = defaultdict(list)
    for mid, rating in db.execute("SELECT oi.meal_id, mr.rating FROM meal_ratings mr "
                                  "JOIN order_items oi USING (order_item_id)"):
        per_meal[mid].append(rating)
    names = {r[1]: r[0] for r in db.execute("SELECT meal_id, name FROM meals")}
    for r in rows:
        v = per_meal[names[r["name"]]]
        assert r["n_ratings"] == len(v)
        assert r["shrunk_rating"] == pytest.approx((sum(v) + 20 * mu) / (len(v) + 20), abs=0.0006)
    for slot in ("breakfast", "lunch", "dinner", "snack"):
        ranks = [r["rank_in_slot"] for r in rows if r["meal_type"] == slot]
        assert ranks == list(range(1, len(ranks) + 1))
        scores = [r["shrunk_rating"] for r in rows if r["meal_type"] == slot]
        assert scores == sorted(scores, reverse=True)


def test_ingredient_effects_match_python(db):
    per_meal = defaultdict(lambda: [0, 0, 0])
    for mid, rating in db.execute(
            "SELECT oi.meal_id, mr.rating FROM meal_ratings mr "
            "JOIN order_items oi USING (order_item_id) JOIN orders o USING (order_id) "
            "WHERE o.delivery_status = 'on_time'"):
        a = per_meal[mid]
        a[0] += 1
        a[1] += rating
        a[2] += rating * rating
    tn = sum(a[0] for a in per_meal.values())
    ts = sum(a[1] for a in per_meal.values())
    tss = sum(a[2] for a in per_meal.values())
    meals_of = defaultdict(list)
    for mid, iid in db.execute("SELECT meal_id, ingredient_id FROM meal_ingredients"):
        meals_of[iid].append(mid)
    names = {r[0]: r[1] for r in db.execute("SELECT ingredient_id, name FROM ingredients")}
    expected = {}
    for iid, meals in meals_of.items():
        n = sum(per_meal[m][0] for m in meals if m in per_meal)
        s = sum(per_meal[m][1] for m in meals if m in per_meal)
        ss = sum(per_meal[m][2] for m in meals if m in per_meal)
        if n < 100 or tn - n < 100:
            continue
        mw, mo = s / n, (ts - s) / (tn - n)
        vw, vo = ss / n - mw * mw, (tss - ss) / (tn - n) - mo * mo
        expected[names[iid]] = (mw - mo, (mw - mo) / math.sqrt(vw / n + vo / (tn - n)))
    rows = analytics(db, "11_ingredient_effects")
    assert {r["ingredient"] for r in rows} == set(expected)
    for r in rows:
        lift, z = expected[r["ingredient"]]
        assert r["lift"] == pytest.approx(lift, abs=0.0006)
        assert r["z_score"] == pytest.approx(z, abs=0.06)
    lifts = [r["lift"] for r in rows]
    assert lifts == sorted(lifts)


def test_delivery_by_zone_matches_python(db):
    late = defaultdict(lambda: [0, 0, 0])
    for zone, status in db.execute(
            "SELECT z.name, o.delivery_status FROM orders o JOIN subscriptions s USING (subscription_id) "
            "JOIN customers c USING (customer_id) JOIN zones z USING (zone_id)"):
        a = late[zone]
        a[0] += 1
        a[1] += status == "late"
        a[2] += status == "failed"
    rows = analytics(db, "12_delivery_by_zone")
    assert len(rows) == 6
    for r in rows:
        n, lt, fl = late[r["zone"]]
        assert r["orders"] == n
        assert r["late_pct"] == pytest.approx(100 * lt / n, abs=0.006)
        assert r["failed_pct"] == pytest.approx(100 * fl / n, abs=0.006)
    pct = [r["late_pct"] for r in rows]
    assert pct == sorted(pct, reverse=True)


def test_rating_by_delivery_status(db):
    rows = {r["delivery_status"]: r for r in analytics(db, "13_rating_by_delivery_status")}
    assert set(rows) == {"on_time", "late"}          # failed orders cannot be rated
    assert sum(r["rated_items"] for r in rows.values()) == db.execute(
        "SELECT COUNT(*) FROM meal_ratings").fetchone()[0]
    assert rows["on_time"]["cold_on_arrival_pct"] == 0


def test_feedback_tags_cover_all_tagged_ratings(db):
    rows = analytics(db, "14_feedback_tags")
    assert sum(r["mentions"] for r in rows) == db.execute(
        "SELECT COUNT(*) FROM meal_ratings WHERE feedback_tag IS NOT NULL").fetchone()[0]
    assert sum(r["share_of_tagged_pct"] for r in rows) == pytest.approx(100, abs=0.5)


def test_kpis(db):
    k = analytics(db, "00_kpis")[0]
    assert k["customers"] == 1000
    assert k["active_subscriptions"] == db.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE end_date IS NULL").fetchone()[0]
    assert k["as_of"] == AS_OF.isoformat()
