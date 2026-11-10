"""The synthetic data has behaviours deliberately planted in it (see README).
These tests prove the SQL analytics can *recover* them from the raw tables alone,
i.e. the analytics detect real structure rather than echo their own assumptions."""
from __future__ import annotations

from mealsub.db import analytics


def test_zone_f_is_the_worst_zone_for_delivery_and_churn(db):
    zones = analytics(db, "12_delivery_by_zone")
    assert zones[0]["zone"] == "Zone F"
    assert zones[0]["late_pct"] > 2 * zones[1]["late_pct"]
    churn = {r["segment"]: r["churn_per_100_sub_months"]
             for r in analytics(db, "03_churn_by_segment") if r["dimension"] == "delivery_zone"}
    assert max(churn, key=churn.get) == "Zone F"
    assert zones[0]["cancelled_for_delivery_pct"] > min(z["cancelled_for_delivery_pct"] for z in zones)


def test_bad_early_deliveries_predict_later_churn(db):
    rows = {r["bad_deliveries_first_28d"]: r["cancel_rate_pct"]
            for r in analytics(db, "06_delivery_vs_churn")}
    assert rows["0"] < rows["1"] < rows["2+"]


def test_post_pause_window_is_riskier(db):
    rows = {r["period"]: r["churn_per_100_sub_months"] for r in analytics(db, "07_pause_behavior")}
    assert rows["first 14 days after resuming a pause"] > rows["all other at-risk time"]


def test_acquisition_channel_ordering(db):
    churn = {r["segment"]: r["churn_per_100_sub_months"]
             for r in analytics(db, "03_churn_by_segment") if r["dimension"] == "acquisition_channel"}
    assert max(churn, key=churn.get) == "promo"
    assert min(churn, key=churn.get) == "referral"
    value = {r["channel"]: r["avg_ltv_to_date_usd"] for r in analytics(db, "08_customer_value")}
    assert max(value, key=value.get) == "referral"
    assert min(value, key=value.get) == "promo"


def test_late_deliveries_lower_ratings(db):
    rows = {r["delivery_status"]: r["avg_rating"] for r in analytics(db, "13_rating_by_delivery_status")}
    assert rows["on_time"] - rows["late"] > 0.6


def test_delivery_issues_is_a_leading_cancellation_reason(db):
    reasons = analytics(db, "04_cancellation_reasons")
    assert reasons[0]["reason"] in {"delivery_issues", "price"}
    assert {r["reason"] for r in reasons} >= {"delivery_issues", "price", "menu_variety"}


def test_ingredient_taste_effects_are_recovered(db):
    rows = analytics(db, "11_ingredient_effects")
    lift = {r["ingredient"]: r["lift"] for r in rows}
    assert rows[0]["ingredient"] == "okra"                         # strongest planted dislike
    assert rows[0]["z_score"] < -10
    assert lift["tofu"] < -0.2 and lift["eggplant"] < -0.2
    assert lift["salmon"] > 0.25 and lift["shrimp"] > 0.15
    top3 = {r["ingredient"] for r in rows[-4:]}
    assert {"salmon"} & top3


def test_best_and_worst_meals(db):
    meals = analytics(db, "10_meal_ratings")
    worst = {r["name"] for r in meals if r["rank_in_slot"] >= 18 and r["meal_type"] == "dinner"}
    assert "Okra Chickpea Tagine" in worst or "Lamb and Okra Stew" in worst
    assert min(r["shrunk_rating"] for r in meals if "Okra" in r["name"]) < 3.5


def test_survival_declines_realistically(db):
    pct = {r["days"]: r["survival_pct"] for r in analytics(db, "05_survival_curve")}
    assert pct[7] > 98
    assert 55 < pct[90] < 80
    assert pct[270] < pct[90]
