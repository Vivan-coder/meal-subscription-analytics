"""Command-line interface:  python -m mealsub <command>"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import recommend as R
from .db import (ANALYTICS_DIR, DEFAULT_DB, ROOT, analytics, connect, list_analytics, verify)
from .generate import GenConfig, build_database
from .report import write_report

DEFAULT_REPORT = ROOT / "docs" / "index.html"


def _print_table(rows, limit: int | None = None) -> None:
    if not rows:
        print("(no rows)")
        return
    headers = list(rows[0].keys())
    shown = rows if limit is None else rows[:limit]
    data = [[("" if v is None else str(v)) for v in tuple(r)] for r in shown]
    widths = [max(len(h), *(len(r[i]) for r in data)) for i, h in enumerate(headers)]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  ".join("-" * w for w in widths))
    for r in data:
        print("  ".join(c.rjust(w) if c.replace(".", "", 1).replace("-", "", 1).replace("+", "", 1).isdigit()
                        else c.ljust(w) for c, w in zip(r, widths)))
    if limit is not None and len(rows) > limit:
        print(f"... {len(rows) - limit} more rows")


def _need_db(path: Path):
    if not path.exists():
        sys.exit(f"database not found: {path}\nrun `python -m mealsub build` first")
    return connect(path)


def cmd_build(a) -> int:
    cfg = GenConfig(n_customers=a.customers, seed=a.seed)
    stats = build_database(a.db, cfg)
    print(f"built {a.db}  (seed={a.seed})")
    for k, v in stats.items():
        print(f"  {k:<14}{v:>10,}")
    print("integrity audit: all checks passed")
    return 0


def cmd_verify(a) -> int:
    conn = _need_db(a.db)
    bad = 0
    for name, violations in verify(conn):
        print(f"{'OK  ' if violations == 0 else 'FAIL'} {name:<48}{violations}")
        bad += violations > 0
    return 1 if bad else 0


def cmd_query(a) -> int:
    conn = _need_db(a.db)
    if a.name is None:
        print("available analytics queries:")
        for n in list_analytics():
            first = (ANALYTICS_DIR / f"{n}.sql").read_text(encoding="utf-8").splitlines()[0]
            print(f"  {n:<28}{first.lstrip('- ').strip()}")
        return 0
    matches = [n for n in list_analytics() if n.startswith(a.name) or n == a.name]
    if len(matches) != 1:
        sys.exit(f"'{a.name}' matches {len(matches)} queries; use `query` to list them")
    _print_table(analytics(conn, matches[0]), a.limit)
    return 0


def cmd_recommend(a) -> int:
    conn = _need_db(a.db)
    week = date.fromisoformat(a.week) if a.week else R.default_week(conn)
    if a.all:
        s = R.recommend_all(conn, week)
        print(f"planned week of {s['week_start']} for {s['customers']:,} active customers")
        print(f"  fully within +/-{int(s['tolerance'] * 100)}% calories: {s['fully_compliant']:,}")
        for k, v in R.validate(conn, s["tolerance"]).items():
            print(f"  {k:<34}{v:>8,}")
        return 0
    if a.customer is None:
        sys.exit("pass --customer <id> or --all")
    plan = R.plan_week(conn, a.customer, week)
    print(f"customer {plan.customer_id}  target {plan.target_kcal} kcal / {plan.target_protein_g} g protein  "
          f"week of {plan.week_start}")
    for d in plan.days:
        flag = "" if d.within_tolerance else "   (closest available - outside tolerance)"
        print(f"\n{d.plan_date:%a %Y-%m-%d}   {d.calories:.0f} kcal   {d.protein_g:.0f} g protein{flag}")
        for slot in R.SLOT_ORDER:
            if slot in d.meals:
                m = d.meals[slot]
                print(f"  {slot:<10}{m.name:<40}{m.calories:>6.0f} kcal  {m.protein_g:>5.1f} g")
    if plan.unplanned_days:
        print(f"\n{plan.unplanned_days} day(s) could not be planned (menu exhausted)")
    return 0


def cmd_report(a) -> int:
    conn = _need_db(a.db)
    out = write_report(conn, a.out)
    print(f"wrote {out}")
    return 0


def cmd_all(a) -> int:
    cmd_build(a)
    conn = connect(a.db)
    s = R.recommend_all(conn)
    print(f"recommendations: {s['customers']:,} customers planned for week of {s['week_start']}")
    conn.close()
    return cmd_report(a)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mealsub", description="Meal-subscription SQL analytics project")
    p.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="generate the synthetic database")
    b.add_argument("--customers", type=int, default=2000)
    b.add_argument("--seed", type=int, default=42)
    b.set_defaults(fn=cmd_build)

    sub.add_parser("verify", help="run the data-integrity audit").set_defaults(fn=cmd_verify)

    q = sub.add_parser("query", help="run an analytics query (omit name to list)")
    q.add_argument("name", nargs="?", help="e.g. 02 or 02_cohort_retention")
    q.add_argument("--limit", type=int, default=40)
    q.set_defaults(fn=cmd_query)

    r = sub.add_parser("recommend", help="weekly meal-plan recommender")
    r.add_argument("--customer", type=int)
    r.add_argument("--all", action="store_true", help="plan every active customer and audit the result")
    r.add_argument("--week", help="Monday of the week to plan (default: first Monday after as_of)")
    r.set_defaults(fn=cmd_recommend)

    rp = sub.add_parser("report", help="write the HTML dashboard")
    rp.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    rp.set_defaults(fn=cmd_report)

    al = sub.add_parser("all", help="build + recommend + report")
    al.add_argument("--customers", type=int, default=2000)
    al.add_argument("--seed", type=int, default=42)
    al.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    al.set_defaults(fn=cmd_all)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
