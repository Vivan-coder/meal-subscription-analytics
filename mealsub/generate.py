"""Deterministic synthetic-data generator.

The generator simulates a meal-subscription business week by week. It is a
*behavioural simulation*, not random noise: delivery problems, low ratings and
pauses change a subscriber's chance of cancelling, so the analytics have real
structure to recover. The planted effects are documented in the README and are
verified by ``tests/test_planted_effects.py``.

Everything is driven by a single seeded ``random.Random`` -> identical output for
the same ``(seed, n_customers)`` on any platform.
"""
from __future__ import annotations

import itertools
import math
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from . import catalog
from .db import assert_valid, connect, init_schema, install_triggers

# ----------------------------------------------------------- model parameters --
BASE_WEEKLY_HAZARD = 0.0115          # baseline weekly cancellation probability
CHANNELS = ["organic", "referral", "paid_social", "promo"]
CHANNEL_WEIGHTS = [0.35, 0.20, 0.25, 0.20]
CHANNEL_HAZARD_MULT = {"organic": 1.0, "referral": 0.7, "paid_social": 1.15, "promo": 1.5}
GOALS = ["lose_weight", "maintain", "build_muscle"]
GOAL_WEIGHTS = [0.40, 0.35, 0.25]
PROTEIN_SHARE = {"lose_weight": 0.28, "maintain": 0.22, "build_muscle": 0.30}
PLAN_WEIGHTS = [0.30, 0.45, 0.25]
REASONS = ["price", "menu_variety", "delivery_issues", "goal_reached", "relocation", "other"]
REASON_WEIGHTS = {"price": 0.28, "menu_variety": 0.20, "delivery_issues": 0.08,
                  "goal_reached": 0.16, "relocation": 0.10, "other": 0.18}
ALLERGEN_WEIGHTS = {"gluten": 0.20, "dairy": 0.25, "tree_nuts": 0.12, "eggs": 0.10, "fish": 0.08,
                    "shellfish": 0.08, "soy": 0.06, "sesame": 0.06, "peanuts": 0.05}
MIN_ELIGIBLE_PER_SLOT = 7            # every customer can always be served & re-planned
P_PAUSE_PER_WEEK = 0.025
P_RESUBSCRIBE = 0.12
FIRST_NAMES = [
    "Aisha", "Omar", "Layla", "Yusuf", "Mariam", "Hassan", "Noor", "Khalid", "Sara", "Ali",
    "Fatima", "Zayed", "Huda", "Tariq", "Dina", "Rashid", "Lina", "Majed", "Reem", "Salman",
    "Emma", "Liam", "Sofia", "Noah", "Mia", "Lucas", "Priya", "Arjun", "Mei", "Kenji",
    "Elena", "Mateo", "Amara", "Daniel", "Chloe", "Ravi", "Hana", "Ivan", "Zoe", "Samir",
]
LAST_NAMES = [
    "Haddad", "Mansoor", "Khalil", "Nasser", "Farouk", "Saleh", "Rahman", "Qureshi", "Ibrahim", "Sayegh",
    "Smith", "Garcia", "Chen", "Patel", "Kim", "Rossi", "Novak", "Silva", "Okafor", "Larsen",
    "Meyer", "Dubois", "Tanaka", "Singh", "Costa", "Ahmed", "Hussein", "Karimi", "Bakr", "Yilmaz",
]


@dataclass(frozen=True)
class GenConfig:
    n_customers: int = 2000
    seed: int = 42
    as_of: date = date(2025, 12, 31)
    signup_start: date = date(2024, 10, 1)
    signup_end: date = date(2025, 12, 31)


@dataclass
class _Customer:
    customer_id: int
    signup: date
    plan_idx: int
    zone_idx: int
    channel: str
    eligible: dict          # slot -> list[meal_id]
    eligible_w: dict        # slot -> list[float]
    propensity: float
    bias: float


@dataclass
class _Rows:
    customers: list = field(default_factory=list)
    cust_allergens: list = field(default_factory=list)
    cust_dislikes: list = field(default_factory=list)
    subscriptions: list = field(default_factory=list)
    pauses: list = field(default_factory=list)
    orders: list = field(default_factory=list)
    items: list = field(default_factory=list)
    ratings: list = field(default_factory=list)


class _Generator:
    def __init__(self, cfg: GenConfig) -> None:
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self.rows = _Rows()
        self.next_sub = 1
        self.next_order = 1
        self.next_item = 1
        self.next_pause = 1

        cat = catalog
        self.ing_id = {n: i + 1 for i, n in enumerate(i[0] for i in cat.INGREDIENTS)}
        self.allergen_id = {n: i + 1 for i, n in enumerate(cat.ALLERGENS)}
        ing_allergens = {i[0]: set(i[6]) for i in cat.INGREDIENTS}
        self.meal_type, self.meal_ings, self.meal_allergens = {}, {}, {}
        self.meal_effect, self.meal_pop = {}, {}
        self.meals_by_type = {t: [] for t in ("breakfast", "lunch", "dinner", "snack")}
        for idx, (name, _cuisine, mtype, recipe) in enumerate(cat.MEALS):
            mid = idx + 1
            self.meal_type[mid] = mtype
            self.meals_by_type[mtype].append(mid)
            self.meal_ings[mid] = {self.ing_id[i] for i, _ in recipe}
            self.meal_allergens[mid] = set().union(*(ing_allergens[i] for i, _ in recipe))
            planted = sum(cat.PLANTED_INGREDIENT_EFFECT.get(i, 0.0) for i, _ in recipe)
            self.meal_effect[mid] = planted + self.rng.gauss(0.0, 0.2)
            self.meal_pop[mid] = math.exp(self.rng.gauss(0.0, 0.35))
        self.zone_late = [z[1] for z in cat.ZONES]

    # ------------------------------------------------------------- profiles --
    def _draw_profile(self, plan_idx: int):
        rng = self.rng
        slots = catalog.PLANS[plan_idx][2]
        names = list(ALLERGEN_WEIGHTS)
        weights = [ALLERGEN_WEIGHTS[n] for n in names]
        while True:
            allergens: list[str] = []
            if rng.random() < 0.22:
                want = 1 if rng.random() < 0.8 else 2
                while len(allergens) < want:
                    a = rng.choices(names, weights)[0]
                    if a not in allergens:
                        allergens.append(a)
            n_dis = rng.choices([0, 1, 2, 3], [0.35, 0.35, 0.20, 0.10])[0]
            dislikes = rng.sample(catalog.DISLIKE_POOL, n_dis)
            bad_allergens = set(allergens)
            bad_ings = {self.ing_id[d] for d in dislikes}
            eligible = {
                slot: [m for m in self.meals_by_type[slot]
                       if not (self.meal_allergens[m] & bad_allergens)
                       and not (self.meal_ings[m] & bad_ings)]
                for slot in slots
            }
            if all(len(v) >= MIN_ELIGIBLE_PER_SLOT for v in eligible.values()):
                return sorted(allergens), sorted(dislikes), eligible

    # ----------------------------------------------------------- simulation --
    def _hazard(self, w: int, bad: int, avg_rating, post_pause: bool, channel: str) -> float:
        h = BASE_WEEKLY_HAZARD
        h *= 2.0 if w <= 4 else (1.3 if w <= 12 else 0.85)   # early-life churn
        h *= min(4.0, 1.0 + 0.9 * bad)                       # bad deliveries, last 14d
        if avg_rating is not None and avg_rating < 3.5:      # unhappy with meals
            h *= 1.5
        if post_pause:                                       # first 14d after resuming
            h *= 1.8
        h *= CHANNEL_HAZARD_MULT[channel]
        return min(h, 0.5)

    def _pick_reason(self, bad: int, avg_rating) -> str:
        w = dict(REASON_WEIGHTS)
        if bad > 0:
            w["delivery_issues"] *= 6
        if avg_rating is not None and avg_rating < 3.5:
            w["menu_variety"] *= 3
        return self.rng.choices(REASONS, [w[r] for r in REASONS])[0]

    def _rate(self, cust: _Customer, meal_id: int, status: str) -> int:
        raw = 4.05 + self.meal_effect[meal_id] + cust.bias + self.rng.gauss(0.0, 0.6)
        if status == "late":
            raw -= 0.9
        return int(min(5, max(1, round(raw))))

    def _tag(self, rating: int, status: str):
        rng = self.rng
        if rating <= 2:
            if status == "late" and rng.random() < 0.6:
                return "cold_on_arrival"
            return rng.choice(["bland", "too_salty", "portion_small", "repetitive"])
        if rating == 3:
            return rng.choice(["bland", "too_salty", "portion_small", "repetitive"]) \
                if rng.random() < 0.3 else None
        if rating == 4:
            return "delicious" if rng.random() < 0.15 else None
        r = rng.random()
        return "delicious" if r < 0.35 else ("great_portion" if r < 0.50 else None)

    def _make_order(self, sub_id: int, cust: _Customer, slots, price: int,
                    day: date, prev: dict, recent: list) -> None:
        rng, rows, cfg = self.rng, self.rows, self.cfg
        r = rng.random()
        p_late = self.zone_late[cust.zone_idx]
        p_fail = p_late / 5.0
        status = "failed" if r < p_fail else ("late" if r < p_fail + p_late else "on_time")
        order_id = self.next_order
        self.next_order += 1
        rows.orders.append((order_id, sub_id, day.isoformat(), status,
                            0 if status == "failed" else price))
        ratings_today = []
        for slot in slots:
            pool, wts = cust.eligible[slot], cust.eligible_w[slot]
            meal = rng.choices(pool, wts)[0]
            while meal == prev.get(slot):
                meal = rng.choices(pool, wts)[0]
            prev[slot] = meal
            item_id = self.next_item
            self.next_item += 1
            rows.items.append((item_id, order_id, meal))
            if status != "failed" and rng.random() < cust.propensity:
                rating = self._rate(cust, meal, status)
                rated_at = min(day + timedelta(days=rng.randint(0, 2)), cfg.as_of)
                rows.ratings.append((item_id, rating, self._tag(rating, status),
                                     rated_at.isoformat()))
                ratings_today.append(rating)
        recent.append((day, 1 if status != "on_time" else 0, ratings_today))

    def _simulate_subscription(self, cust: _Customer, start: date, allow_resub: bool) -> None:
        rng, cfg, rows = self.rng, self.cfg, self.rows
        sub_id = self.next_sub
        self.next_sub += 1
        _name, price, slots = catalog.PLANS[cust.plan_idx]
        one = timedelta(days=1)
        end_date, reason = None, None
        recent: list = []
        prev: dict = {}
        last_resume = None
        week_start, w = start, 0
        while week_start <= cfg.as_of:
            cancel_day, bad = None, 0
            if w >= 1:
                recent = [e for e in recent if e[0] >= week_start - timedelta(days=14)]
                bad = sum(e[1] for e in recent)
                rated = [x for e in recent for x in e[2]]
                avg_rating = sum(rated) / len(rated) if len(rated) >= 2 else None
                post_pause = last_resume is not None and (week_start - last_resume).days < 14
                if rng.random() < self._hazard(w, bad, avg_rating, post_pause, cust.channel):
                    c = week_start + timedelta(days=rng.randint(1, 7))
                    if c <= cfg.as_of:
                        cancel_day = c
                        reason = self._pick_reason(bad, avg_rating)
                if cancel_day is None and (last_resume is None
                                           or (week_start - last_resume).days >= 21):
                    p = P_PAUSE_PER_WEEK * (1.8 if bad > 0 else 1.0)
                    if rng.random() < p:
                        k = rng.choices([1, 2, 3, 4], [0.4, 0.3, 0.2, 0.1])[0]
                        pause_end = week_start + timedelta(days=7 * k)
                        if pause_end <= cfg.as_of + one:
                            rows.pauses.append((self.next_pause, sub_id,
                                                week_start.isoformat(), pause_end.isoformat()))
                            self.next_pause += 1
                            last_resume = pause_end
                            week_start, w = pause_end, w + k
                            continue
            for off in range(7):
                day = week_start + timedelta(days=off)
                if (cancel_day is not None and day >= cancel_day) or day > cfg.as_of:
                    break
                if day.weekday() < 5:
                    self._make_order(sub_id, cust, slots, price, day, prev, recent)
            if cancel_day is not None:
                end_date = cancel_day
                break
            week_start += timedelta(days=7)
            w += 1
        rows.subscriptions.append((sub_id, cust.customer_id, cust.plan_idx + 1,
                                   start.isoformat(),
                                   end_date.isoformat() if end_date else None, reason))
        if (allow_resub and end_date is not None and reason != "relocation"
                and rng.random() < P_RESUBSCRIBE):
            restart = end_date + timedelta(days=rng.randint(30, 120))
            if restart <= cfg.as_of:
                self._simulate_subscription(cust, restart, allow_resub=False)

    # ---------------------------------------------------------------- build --
    def run(self) -> None:
        cfg, rng, rows = self.cfg, self.rng, self.rows
        n_days = (cfg.signup_end - cfg.signup_start).days + 1
        days = [cfg.signup_start + timedelta(days=i) for i in range(n_days)]
        cum = list(itertools.accumulate(1.0 + 1.2 * i / (n_days - 1) for i in range(n_days)))
        signups = sorted(rng.choices(days, cum_weights=cum, k=cfg.n_customers))
        zone_weights = [0.22, 0.20, 0.18, 0.16, 0.14, 0.10]

        for cid, signup in enumerate(signups, start=1):
            plan_idx = rng.choices(range(len(catalog.PLANS)), PLAN_WEIGHTS)[0]
            plan_name = catalog.PLANS[plan_idx][0]
            lo, hi = catalog.PLAN_CALORIE_RANGE[plan_name]
            target = int(round(rng.uniform(lo, hi) / 50.0) * 50)
            goal = rng.choices(GOALS, GOAL_WEIGHTS)[0]
            protein = int(round(target * PROTEIN_SHARE[goal] / 4.0))
            allergens, dislikes, eligible = self._draw_profile(plan_idx)
            zone_idx = rng.choices(range(len(catalog.ZONES)), zone_weights)[0]
            channel = rng.choices(CHANNELS, CHANNEL_WEIGHTS)[0]
            first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
            rows.customers.append((cid, f"{first} {last}",
                                   f"{first.lower()}.{last.lower()}{cid}@example.com",
                                   zone_idx + 1, signup.isoformat(), channel, goal,
                                   target, protein))
            rows.cust_allergens += [(cid, self.allergen_id[a]) for a in allergens]
            rows.cust_dislikes += [(cid, self.ing_id[d]) for d in dislikes]
            cust = _Customer(
                customer_id=cid, signup=signup, plan_idx=plan_idx, zone_idx=zone_idx,
                channel=channel, eligible=eligible,
                eligible_w={s: [self.meal_pop[m] for m in ms] for s, ms in eligible.items()},
                propensity=rng.uniform(0.15, 0.50), bias=rng.gauss(0.0, 0.35),
            )
            self._simulate_subscription(cust, signup, allow_resub=True)


# ------------------------------------------------------------------ persist --
def _load_reference(conn: sqlite3.Connection, g: _Generator) -> None:
    cat = catalog
    conn.executemany("INSERT INTO zones VALUES (?,?)",
                     [(i + 1, z[0]) for i, z in enumerate(cat.ZONES)])
    conn.executemany("INSERT INTO allergens VALUES (?,?)", list(map(lambda kv: (kv[1], kv[0]),
                                                                    g.allergen_id.items())))
    conn.executemany("INSERT INTO ingredients VALUES (?,?,?,?,?,?,?)",
                     [(g.ing_id[i[0]], i[0], i[1], i[2], i[3], i[4], i[5])
                      for i in cat.INGREDIENTS])
    conn.executemany("INSERT INTO ingredient_allergens VALUES (?,?)",
                     [(g.ing_id[i[0]], g.allergen_id[a]) for i in cat.INGREDIENTS for a in i[6]])
    conn.executemany("INSERT INTO meals VALUES (?,?,?,?)",
                     [(idx + 1, m[0], m[1], m[2]) for idx, m in enumerate(cat.MEALS)])
    conn.executemany("INSERT INTO meal_ingredients VALUES (?,?,?)",
                     [(idx + 1, g.ing_id[ing], grams)
                      for idx, m in enumerate(cat.MEALS) for ing, grams in m[3]])
    conn.executemany("INSERT INTO plans VALUES (?,?,?)",
                     [(i + 1, p[0], p[1]) for i, p in enumerate(cat.PLANS)])
    conn.executemany("INSERT INTO plan_slots VALUES (?,?)",
                     [(i + 1, slot) for i, p in enumerate(cat.PLANS) for slot in p[2]])


def build_database(path: str | Path, cfg: GenConfig = GenConfig()) -> dict:
    """Create ``path`` from scratch and fill it. Returns row counts."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    gen = _Generator(cfg)
    gen.run()

    conn = connect(path)
    try:
        conn.execute("PRAGMA journal_mode = MEMORY")
        conn.execute("PRAGMA synchronous = OFF")
        init_schema(conn, triggers=False)   # bulk load first, audit, then arm triggers
        r = gen.rows
        with conn:
            conn.executemany("INSERT INTO meta VALUES (?,?)", [
                ("as_of_date", cfg.as_of.isoformat()), ("seed", str(cfg.seed)),
                ("n_customers", str(cfg.n_customers)), ("currency", "USD"),
            ])
            _load_reference(conn, gen)
            conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?)", r.customers)
            conn.executemany("INSERT INTO customer_allergens VALUES (?,?)", r.cust_allergens)
            conn.executemany("INSERT INTO customer_dislikes VALUES (?,?)", r.cust_dislikes)
            conn.executemany("INSERT INTO subscriptions VALUES (?,?,?,?,?,?)",
                             sorted(r.subscriptions))
            conn.executemany("INSERT INTO subscription_pauses VALUES (?,?,?,?)", r.pauses)
            conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", r.orders)
            conn.executemany("INSERT INTO order_items VALUES (?,?,?)", r.items)
            conn.executemany("INSERT INTO meal_ratings VALUES (?,?,?,?)", r.ratings)
        conn.execute("ANALYZE")          # planner statistics make the audit fast
        assert_valid(conn)
        install_triggers(conn)
        problems = conn.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise RuntimeError(f"foreign key violations after build: {len(problems)}")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite integrity_check failed")
        conn.commit()
        return {
            "customers": len(r.customers), "subscriptions": len(r.subscriptions),
            "pauses": len(r.pauses), "orders": len(r.orders),
            "order_items": len(r.items), "ratings": len(r.ratings),
        }
    finally:
        conn.close()
