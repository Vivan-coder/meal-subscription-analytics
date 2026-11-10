"""Constraint-aware weekly meal-plan recommender.

Division of labour
------------------
SQL    : hard constraints (plan slots, allergens, disliked ingredients), nutrition,
         meal quality (Bayesian-shrunk ratings) and personal cuisine affinity.
Python : the small combinatorial search that picks one meal per slot per day.

Hard constraints (never violated)
    * only meals of the plan's slots, one per slot per day
    * no allergen, no disliked ingredient
    * no meal repeated within the planned week
Targets (searched for, reported on)
    * each day's calories within +/- ``tolerance`` of the customer's target (10%)
Soft preferences (the objective being maximised per day)
    * meal quality + 0.5 x personal cuisine affinity
    * -0.75 for a meal eaten in the previous 14 days
    * -3 x relative calorie deviation, -0.01 per gram of protein shortfall
"""
from __future__ import annotations

import itertools
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable

from .db import RECOMMEND_DIR, as_of, query

DEFAULT_TOLERANCE = 0.10
AFFINITY_WEIGHT = 0.5
RECENT_PENALTY = 0.75
CALORIE_WEIGHT = 3.0
PROTEIN_WEIGHT = 0.01
STAGES = (8, 14, 24)             # candidates per slot tried, widening on failure
MAX_COMBINATIONS = 300_000
SLOT_ORDER = ("breakfast", "lunch", "dinner", "snack")


@dataclass(frozen=True)
class Candidate:
    meal_id: int
    name: str
    cuisine: str
    meal_type: str
    calories: float
    protein_g: float
    score: float


@dataclass
class DayPlan:
    plan_date: date
    meals: dict                      # meal_type -> Candidate
    calories: float
    protein_g: float
    within_tolerance: bool


@dataclass
class WeekPlan:
    customer_id: int
    week_start: date
    target_kcal: int
    target_protein_g: int
    days: list = field(default_factory=list)
    unplanned_days: int = 0

    @property
    def fully_compliant(self) -> bool:
        return self.unplanned_days == 0 and all(d.within_tolerance for d in self.days)


def next_monday(d: date) -> date:
    return d + timedelta(days=(7 - d.weekday()) % 7 or 7)


def _search(pools: dict, slots: list, target: float, protein_target: float,
            tolerance: float):
    """Best combination (one per slot) inside the calorie band, else the closest."""
    best_valid, best_valid_val = None, -math.inf
    best_any, best_any_dev = None, math.inf
    for combo in itertools.product(*(pools[s] for s in slots)):
        kcal = sum(c.calories for c in combo)
        dev = abs(kcal - target) / target
        if dev < best_any_dev - 1e-12:
            best_any, best_any_dev = combo, dev
        if dev <= tolerance + 1e-12:
            protein = sum(c.protein_g for c in combo)
            val = (sum(c.score for c in combo) - CALORIE_WEIGHT * dev
                   - PROTEIN_WEIGHT * max(0.0, protein_target - protein))
            if val > best_valid_val + 1e-12:
                best_valid, best_valid_val = combo, val
    return best_valid, best_any


def _choose_day(pools: dict, slots: list, target: float, protein_target: float,
                tolerance: float):
    """Returns (combo, within_tolerance) or (None, False) if a slot has no meal left."""
    if any(not pools[s] for s in slots):
        return None, False
    closest = None
    for k in STAGES:
        trimmed = {s: pools[s][:k] for s in slots}
        if math.prod(len(v) for v in trimmed.values()) > MAX_COMBINATIONS:
            break
        valid, any_combo = _search(trimmed, slots, target, protein_target, tolerance)
        if valid is not None:
            return valid, True
        closest = any_combo
        if all(len(pools[s]) <= k for s in slots):
            break
    return closest, False


def customer_context(conn: sqlite3.Connection, customer_id: int):
    row = conn.execute(
        """SELECT c.daily_calorie_target, c.protein_target_g, s.plan_id
           FROM customers c
           JOIN subscriptions s ON s.customer_id = c.customer_id AND s.end_date IS NULL
           WHERE c.customer_id = ?""", (customer_id,)).fetchone()
    if row is None:
        raise ValueError(f"customer {customer_id} does not exist or has no active subscription")
    slots = [r[0] for r in conn.execute(
        "SELECT meal_type FROM plan_slots WHERE plan_id = ?", (row["plan_id"],))]
    slots.sort(key=SLOT_ORDER.index)
    return row["daily_calorie_target"], row["protein_target_g"], row["plan_id"], slots


def meal_quality(conn: sqlite3.Connection) -> dict:
    """Global per-meal quality (shrunk rating); computed once per run."""
    return {r[0]: r[1] for r in conn.execute("SELECT meal_id, shrunk_rating FROM v_meal_rating")}


def plan_week(conn: sqlite3.Connection, customer_id: int, week_start: date,
              tolerance: float = DEFAULT_TOLERANCE, quality: dict | None = None) -> WeekPlan:
    """Plan Monday-Friday of the week starting ``week_start`` (must be a Monday)."""
    if week_start.weekday() != 0:
        raise ValueError(f"week_start must be a Monday, got {week_start} ({week_start:%A})")
    target, protein_target, plan_id, slots = customer_context(conn, customer_id)
    quality = quality if quality is not None else meal_quality(conn)

    affinity = {r["cuisine"]: r["affinity"]
                for r in query(conn, RECOMMEND_DIR / "cuisine_affinity.sql",
                               {"customer_id": customer_id})}
    recent = {r[0] for r in query(conn, RECOMMEND_DIR / "recent_meals.sql",
                                  {"customer_id": customer_id,
                                   "since": (week_start - timedelta(days=14)).isoformat()})}
    pools_all: dict = {s: [] for s in slots}
    for r in query(conn, RECOMMEND_DIR / "eligible_meals.sql",
                   {"customer_id": customer_id, "plan_id": plan_id}):
        score = (quality[r["meal_id"]] + AFFINITY_WEIGHT * affinity.get(r["cuisine"], 0.0)
                 - (RECENT_PENALTY if r["meal_id"] in recent else 0.0))
        pools_all[r["meal_type"]].append(
            Candidate(r["meal_id"], r["name"], r["cuisine"], r["meal_type"],
                      r["calories"], r["protein_g"], score))
    for s in slots:
        pools_all[s].sort(key=lambda c: (-c.score, c.meal_id))

    plan = WeekPlan(customer_id, week_start, target, protein_target)
    used: set = set()
    for offset in range(5):
        day = week_start + timedelta(days=offset)
        pools = {s: [c for c in pools_all[s] if c.meal_id not in used] for s in slots}
        combo, ok = _choose_day(pools, slots, float(target), float(protein_target), tolerance)
        if combo is None:
            plan.unplanned_days += 1
            continue
        used.update(c.meal_id for c in combo)
        plan.days.append(DayPlan(day, {c.meal_type: c for c in combo},
                                 round(sum(c.calories for c in combo), 1),
                                 round(sum(c.protein_g for c in combo), 1), ok))
    return plan


def save_plan(conn: sqlite3.Connection, plan: WeekPlan) -> None:
    dates = [(plan.week_start + timedelta(days=i)).isoformat() for i in range(5)]
    conn.executemany("DELETE FROM recommended_plans WHERE customer_id = ? AND plan_date = ?",
                     [(plan.customer_id, d) for d in dates])
    conn.executemany(
        "INSERT INTO recommended_plans (customer_id, plan_date, meal_type, meal_id) VALUES (?,?,?,?)",
        [(plan.customer_id, d.plan_date.isoformat(), t, c.meal_id)
         for d in plan.days for t, c in d.meals.items()])


def active_customers(conn: sqlite3.Connection) -> list[int]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT customer_id FROM subscriptions WHERE end_date IS NULL ORDER BY 1")]


def default_week(conn: sqlite3.Connection) -> date:
    """The first Monday after the dataset's as_of date."""
    return next_monday(date.fromisoformat(as_of(conn)))


def recommend_all(conn: sqlite3.Connection, week_start: date | None = None,
                  tolerance: float = DEFAULT_TOLERANCE,
                  customers: Iterable[int] | None = None) -> dict:
    """Plan and persist a week for every active customer; returns a summary."""
    week_start = week_start or default_week(conn)
    quality = meal_quality(conn)
    ids = list(customers) if customers is not None else active_customers(conn)
    compliant = 0
    with conn:
        for cid in ids:
            plan = plan_week(conn, cid, week_start, tolerance, quality)
            save_plan(conn, plan)
            compliant += plan.fully_compliant
    return {"week_start": week_start.isoformat(), "customers": len(ids),
            "fully_compliant": compliant, "tolerance": tolerance}


def validate(conn: sqlite3.Connection, tolerance: float = DEFAULT_TOLERANCE) -> dict:
    rows = query(conn, RECOMMEND_DIR / "validate_plans.sql", {"tolerance": tolerance})
    return {r[0]: r[1] for r in rows}
