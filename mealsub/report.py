"""Builds a single self-contained HTML dashboard (no JS, no external assets).

Every number on the page comes from a query in ``sql/analytics`` or
``sql/recommend``; this module only lays results out. Colours follow a
validated palette: one blue hue for magnitude, a blue<->red diverging pair with a
neutral midpoint for lift, light/dark selected via CSS custom properties.
"""
from __future__ import annotations

import math
import sqlite3
from datetime import date, timedelta
from html import escape as esc
from pathlib import Path

from . import recommend as R
from .db import analytics, as_of

CSS = """
:root{color-scheme:light;--bg:#f6f5f2;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#7a7873;
--line:#e3e1db;--grid:#ecebe6;--accent:#2a78d6;--accent-ink:#ffffff;--neg:#d03b3b;--pos:#2a78d6;--mid:#f0efec;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#121211;--surface:#1a1a19;
--ink:#f0efec;--ink2:#c3c2b7;--muted:#9c9a92;--line:#32322f;--grid:#2a2a28;--accent:#3987e5;--accent-ink:#0b0b0b;
--neg:#e66767;--pos:#3987e5;--mid:#383835;}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#121211;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#9c9a92;
--line:#32322f;--grid:#2a2a28;--accent:#3987e5;--accent-ink:#0b0b0b;--neg:#e66767;--pos:#3987e5;--mid:#383835;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:28px;margin:0 0 4px;letter-spacing:-.01em}
h2{font-size:18px;margin:0 0 4px}
.sub{color:var(--ink2);margin:0 0 24px;max-width:70ch}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:24px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.kpi .v{font-size:26px;font-weight:650;letter-spacing:-.01em;font-variant-numeric:tabular-nums}
.kpi .l{color:var(--ink2);font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:16px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px 18px 16px;margin-bottom:16px;overflow:hidden}
.grid .card{margin-bottom:0}
.card p.note{color:var(--ink2);font-size:13px;margin:2px 0 12px}
.card p.take{font-size:13px;margin:10px 0 0;color:var(--ink2)}
.card p.take b{color:var(--ink)}
svg{display:block;width:100%;height:auto;overflow:visible}
svg text{fill:var(--ink2);font:12px system-ui,sans-serif}
svg .axis{stroke:var(--line)} svg .gridl{stroke:var(--grid)}
svg .lbl{fill:var(--ink)}
table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th,td{padding:5px 8px;text-align:right;border-bottom:1px solid var(--grid);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{color:var(--ink2);font-weight:600}
.scroll{overflow-x:auto}
.heat td{padding:0;border:2px solid var(--surface);text-align:center;min-width:44px;height:30px;font-size:12px}
.heat th{border:none}
.hbar{display:grid;grid-template-columns:130px 1fr 64px;gap:8px;align-items:center;margin:5px 0;font-size:13px}
.hbar .t{background:var(--grid);border-radius:4px;height:14px;position:relative}
.hbar .f{background:var(--accent);height:14px;border-radius:0 4px 4px 0;min-width:2px}
.hbar .n{text-align:right;font-variant-numeric:tabular-nums}
.lift{display:grid;grid-template-columns:120px 1fr 52px;gap:8px;align-items:center;margin:4px 0;font-size:13px}
.lift .axis{position:relative;height:14px;background:linear-gradient(var(--line),var(--line)) center/1px 100% no-repeat}
.lift .b{position:absolute;top:0;height:14px}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;border:1px solid var(--line);color:var(--ink2)}
.ok{color:var(--ink)} footer{color:var(--muted);font-size:12px;margin-top:24px}
a{color:var(--accent)}
"""


# ----------------------------------------------------------------- helpers --
def _money(x: float) -> str:
    return f"${x:,.0f}"


def _nice_step(span: float, ticks: int = 4) -> float:
    raw = span / ticks
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def _line_chart(points: list, y_fmt, y_title: str, width: int = 720, height: int = 270,
                y_min: float | None = 0, label_last: bool = True) -> str:
    """points: [(x_label, value, tooltip)] -> inline SVG."""
    ml, mr, mt, mb = 56, 40, 14, 34
    w, h = width - ml - mr, height - mt - mb
    ys = [p[1] for p in points]
    lo = y_min if y_min is not None else min(ys)
    hi = max(ys)
    step = _nice_step(max(hi - lo, 1e-9))
    top = math.ceil(hi / step) * step
    lo = math.floor(lo / step) * step if y_min is None else lo
    xs = [ml + (i / max(len(points) - 1, 1)) * w for i in range(len(points))]

    def y(v: float) -> float:
        return mt + h - (v - lo) / (top - lo) * h

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(y_title)}">']
    t = lo
    while t <= top + 1e-9:
        out.append(f'<line class="gridl" x1="{ml}" x2="{ml + w}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>')
        out.append(f'<text x="{ml - 8}" y="{y(t) + 4:.1f}" text-anchor="end">{esc(y_fmt(t))}</text>')
        t += step
    every = max(1, math.ceil(len(points) / 7))
    for i, (xl, _v, _tip) in enumerate(points):
        if i % every == 0 or i == len(points) - 1:
            out.append(f'<text x="{xs[i]:.1f}" y="{height - 10}" text-anchor="middle">{esc(str(xl))}</text>')
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y(p[1]):.1f}" for i, (x, p) in enumerate(zip(xs, points)))
    out.append(f'<path d="{path}" fill="none" stroke="var(--accent)" stroke-width="2" '
               f'stroke-linejoin="round" stroke-linecap="round"/>')
    for x, p in zip(xs, points):
        out.append(f'<g><title>{esc(p[2])}</title><circle cx="{x:.1f}" cy="{y(p[1]):.1f}" r="12" fill="transparent"/>'
                   f'<circle cx="{x:.1f}" cy="{y(p[1]):.1f}" r="3.5" fill="var(--accent)" '
                   f'stroke="var(--surface)" stroke-width="2"/></g>')
    if label_last:
        lx, lp = xs[-1], points[-1]
        out.append(f'<text class="lbl" x="{lx:.1f}" y="{y(lp[1]) - 10:.1f}" text-anchor="end" '
                   f'font-weight="600">{esc(y_fmt(lp[1]))}</text>')
    out.append("</svg>")
    return "".join(out)


def _hbars(rows: list, fmt=lambda v: f"{v:.1f}", vmax: float | None = None) -> str:
    """rows: [(label, value, tooltip)] -> CSS bars (zero-based, direct value labels)."""
    vmax = vmax or max(r[1] for r in rows) or 1
    out = []
    for label, val, tip in rows:
        out.append(f'<div class="hbar" title="{esc(tip)}"><span>{esc(str(label))}</span>'
                   f'<span class="t"><span class="f" style="display:block;width:{max(val / vmax * 100, 0.5):.1f}%"></span></span>'
                   f'<span class="n">{esc(fmt(val))}</span></div>')
    return "".join(out)


def _table(headers: list, rows: list) -> str:
    def numeric(c) -> bool:
        t = str(c).replace(",", "").replace(".", "").lstrip("$+-").rstrip("%")
        return t == "" or t.isdigit()

    left = [i == 0 or any(not numeric(r[i]) for r in rows) for i in range(len(headers))]
    style = [' style="text-align:left"' if lf else "" for lf in left]
    head = "".join(f"<th{style[i]}>{esc(h)}</th>" for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(f"<td{style[i]}>{esc(str(c))}</td>" for i, c in enumerate(r)) + "</tr>"
                   for r in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _kpi(value: str, label: str) -> str:
    return f'<div class="kpi"><div class="v">{esc(value)}</div><div class="l">{esc(label)}</div></div>'


def _heatmap(rows: list) -> str:
    cohorts = sorted({r["cohort"] for r in rows})
    kmax = max(r["month_offset"] for r in rows)
    cell = {(r["cohort"], r["month_offset"]): r for r in rows}
    head = "<th>Cohort</th><th>Size</th>" + "".join(f"<th>M{k}</th>" for k in range(kmax + 1))
    body = []
    for c in cohorts:
        size = next(r["cohort_size"] for r in rows if r["cohort"] == c)
        tds = [f"<td style='padding:0 8px;text-align:left'>{esc(c)}</td>",
               f"<td style='padding:0 8px'>{size}</td>"]
        for k in range(kmax + 1):
            r = cell.get((c, k))
            if r is None:
                tds.append("<td></td>")
                continue
            p = r["retention_pct"]
            mix = 8 + 0.92 * p      # 0% -> faint tint, 100% -> full accent
            ink = "var(--accent-ink)" if p >= 62 else "var(--ink)"
            tds.append(f'<td title="{esc(c)} cohort, month {k}: {r["retained"]} of {size} retained ({p}%)" '
                       f'style="background:color-mix(in srgb,var(--accent) {mix:.0f}%,var(--surface));color:{ink}">'
                       f'{p:.0f}</td>')
        body.append("<tr>" + "".join(tds) + "</tr>")
    return f'<div class="scroll"><table class="heat"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def _lift_chart(rows: list) -> str:
    if not rows:
        return "<p class='note'>No ingredient has a statistically significant effect in this dataset.</p>"
    vmax = max(abs(r["lift"]) for r in rows) or 1
    out = []
    for r in rows:
        v = r["lift"]
        width = abs(v) / vmax * 50
        pos = v >= 0
        style = (f"left:50%;width:{width:.1f}%;background:var(--pos);border-radius:0 4px 4px 0" if pos else
                 f"right:50%;width:{width:.1f}%;background:var(--neg);border-radius:4px 0 0 4px")
        tip = (f"{r['ingredient']}: {v:+.2f} rating points vs meals without it "
               f"({r['ratings_with']:,} ratings, z = {r['z_score']})")
        out.append(f'<div class="lift" title="{esc(tip)}"><span>{esc(r["ingredient"])}</span>'
                   f'<span class="axis"><span class="b" style="{style}"></span></span>'
                   f'<span style="text-align:right">{v:+.2f}</span></div>')
    return "".join(out)


# --------------------------------------------------------------- the report --
def build_report(conn: sqlite3.Connection) -> str:
    kpi = analytics(conn, "00_kpis")[0]
    monthly = analytics(conn, "01_monthly_revenue")
    cohort = analytics(conn, "02_cohort_retention")
    churn = analytics(conn, "03_churn_by_segment")
    reasons = analytics(conn, "04_cancellation_reasons")
    survival = analytics(conn, "05_survival_curve")
    delivery_churn = analytics(conn, "06_delivery_vs_churn")
    pause = analytics(conn, "07_pause_behavior")
    value = analytics(conn, "08_customer_value")
    pareto = analytics(conn, "09_revenue_concentration")
    meals = analytics(conn, "10_meal_ratings")
    lifts = analytics(conn, "11_ingredient_effects")
    zones = analytics(conn, "12_delivery_by_zone")
    by_status = analytics(conn, "13_rating_by_delivery_status")

    surv90 = next((r["survival_pct"] for r in survival if r["days"] == 90), None)
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
             f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>Meal Subscription Analytics</title><style>{CSS}</style></head><body><div class='wrap'>"]
    parts.append("<h1>Meal Subscription Analytics</h1>")
    parts.append(f"<p class='sub'>Pure-SQL analytics on a <b>synthetic</b> meal-plan subscription business "
                 f"({kpi['first_order']} &rarr; {kpi['as_of']}). Every figure below is the output of a query in "
                 f"<code>sql/analytics</code>; nothing is hand-entered.</p>")
    parts.append("<div class='kpis'>" + "".join([
        _kpi(f"{kpi['customers']:,}", "customers"),
        _kpi(f"{kpi['active_subscriptions']:,}", "active subscriptions"),
        _kpi(_money(kpi["total_revenue_usd"]), "revenue to date"),
        _kpi(f"{kpi['on_time_pct']}%", "on-time deliveries"),
        _kpi(f"{kpi['avg_rating']}", f"avg rating ({kpi['ratings']:,} ratings)"),
        _kpi(f"{surv90}%", "subscriptions surviving 90 days"),
    ]) + "</div>")

    # --- revenue ---------------------------------------------------------
    rev_pts = [(date.fromisoformat(r["month"] + "-01").strftime("%b %y"), r["revenue_usd"],
                f"{r['month']}: {_money(r['revenue_usd'])} revenue, {r['active_subscribers']:,} active subscribers, "
                f"{r['orders']:,} orders") for r in monthly]
    parts.append("<div class='card'><h2>Monthly revenue</h2><p class='note'>Sum of delivered-order amounts "
                 "(failed deliveries are refunded).</p>"
                 + _line_chart(rev_pts, lambda v: f"${v / 1000:,.0f}k", "Monthly revenue in US dollars")
                 + _table(["Month", "Active subs", "New", "Reactivated", "Cancelled", "Revenue", "MoM", "ARPU", "On-time"],
                          [(r["month"], f"{r['active_subscribers']:,}", r["new_customers"], r["reactivations"],
                            r["cancellations"], _money(r["revenue_usd"]),
                            "" if r["mom_growth_pct"] is None else f"{r['mom_growth_pct']:+.1f}%",
                            f"${r['arpu_usd']:,.0f}", f"{r['on_time_pct']}%") for r in monthly[-6:]])
                 + "<p class='take'>Last six months shown; the full series is in <code>01_monthly_revenue.sql</code>.</p></div>")

    # --- cohorts ---------------------------------------------------------
    parts.append("<div class='card'><h2>Cohort retention</h2><p class='note'>% of each signup-month cohort still holding "
                 "an active subscription at month end (M0 = end of signup month). Stronger blue = higher retention.</p>"
                 + _heatmap(cohort) + "</div>")

    # --- churn -----------------------------------------------------------
    def seg(dim):
        return [(r["segment"].replace("_", " "), r["churn_per_100_sub_months"],
                 f"{r['cancellations']} cancellations over {r['subscriber_months']:,.0f} subscriber-months")
                for r in churn if r["dimension"] == dim]

    ch, zn = seg("acquisition_channel"), seg("delivery_zone")
    vmax = max(r[1] for r in ch + zn)
    parts.append("<div class='grid'>")
    parts.append("<div class='card'><h2>Churn by acquisition channel</h2><p class='note'>Cancellations per 100 "
                 "subscriber-months at risk (exposure-adjusted).</p>" + _hbars(ch, lambda v: f"{v:.1f}", vmax) + "</div>")
    parts.append("<div class='card'><h2>Churn by delivery zone</h2><p class='note'>Same measure. Zone F stands out.</p>"
                 + _hbars(zn, lambda v: f"{v:.1f}", vmax) + "</div></div><div style='height:16px'></div>")

    parts.append("<div class='grid'>")
    dc = [(f"{r['bad_deliveries_first_28d']} late/failed", r["cancel_rate_pct"],
           f"{r['cancelled_day_28_to_90']} of {r['subscriptions']} cancelled between day 28 and 90") for r in delivery_churn]
    parts.append("<div class='card'><h2>Bad deliveries predict churn</h2><p class='note'>Share cancelling in days 28-90, by number "
                 "of late/failed deliveries in the first 28 days (only subscriptions that survived day 28).</p>"
                 + _hbars(dc, lambda v: f"{v:.1f}%") + "</div>")
    pz = [(r["period"].replace("first 14 days after resuming a pause", "14d after resume")
           .replace("all other at-risk time", "all other time"), r["churn_per_100_sub_months"],
           f"{r['cancellations']} cancellations over {r['subscriber_months']:,} subscriber-months") for r in pause]
    parts.append("<div class='card'><h2>Post-pause risk window</h2><p class='note'>Cancellations per 100 subscriber-months.</p>"
                 + _hbars(pz, lambda v: f"{v:.1f}") + "</div></div><div style='height:16px'></div>")

    surv_pts = [(f"{r['days']}d", r["survival_pct"],
                 f"{r['survival_pct']}% of {r['observable_subscriptions']:,} observable subscriptions lasted {r['days']}+ days")
                for r in survival]
    parts.append("<div class='card'><h2>Subscription survival</h2><p class='note'>Share of subscriptions that last at least N days "
                 "(only those old enough to be observed for N days).</p>"
                 + _line_chart(surv_pts, lambda v: f"{v:.0f}%", "Survival percentage by subscription age", y_min=0)
                 + "</div>")

    rs = [(r["reason"].replace("_", " "), r["share_pct"], f"{r['cancellations']} cancellations") for r in reasons]
    parts.append("<div class='grid'><div class='card'><h2>Why subscribers cancel</h2><p class='note'>Share of all cancellations.</p>"
                 + _hbars(rs, lambda v: f"{v:.1f}%") + "</div>"
                 "<div class='card'><h2>Customer value to date, by channel</h2><p class='note'>Average cumulative revenue per customer.</p>"
                 + _hbars([(r["channel"].replace("_", " "), r["avg_ltv_to_date_usd"],
                            f"{r['customers']} customers, {r['still_active_pct']}% still active") for r in value],
                          lambda v: _money(v))
                 + f"<p class='take'>Top 20% of customers generate <b>{pareto[1]['cumulative_share_pct']}%</b> of revenue.</p></div></div>"
                 "<div style='height:16px'></div>")

    # --- feedback --------------------------------------------------------
    sig = [r for r in lifts if r["z_score"] is not None and abs(r["z_score"]) >= 3]
    shown = sig[:6] + sig[-6:] if len(sig) > 12 else sig
    parts.append("<div class='card'><h2>Which ingredients move ratings?</h2><p class='note'>Mean rating of on-time meals containing the "
                 "ingredient minus meals without it (rating points). Blue = higher, red = lower. Showing |z| &ge; 3.</p>"
                 + _lift_chart(shown)
                 + "<p class='take'><b>Read with care:</b> this is a one-ingredient-at-a-time comparison. An ingredient that "
                   "only appears alongside a disliked one (e.g. bulgur beside okra) inherits some of its penalty. A regression "
                   "on all ingredients at once would be the natural next step.</p></div>")

    def top_bottom(mt):
        rows = [r for r in meals if r["meal_type"] == mt]
        return rows[:3] + rows[-2:]

    mrows = []
    for mt in ("breakfast", "lunch", "dinner", "snack"):
        for r in top_bottom(mt):
            mrows.append((mt, r["rank_in_slot"], r["name"], r["cuisine"], f"{r['n_ratings']:,}",
                          f"{r['avg_rating']:.2f}", f"{r['shrunk_rating']:.2f}"))
    parts.append("<div class='card'><h2>Meal leaderboard</h2><p class='note'>Top 3 and bottom 2 per slot by Bayesian-shrunk rating.</p>"
                 + _table(["Slot", "Rank", "Meal", "Cuisine", "Ratings", "Avg", "Shrunk"], mrows) + "</div>")

    zrows = [(r["zone"], f"{r['orders']:,}", f"{r['late_pct']}%", f"{r['failed_pct']}%", r["avg_rating"],
              f"{r['cancelled_for_delivery_pct']}%") for r in zones]
    st = {r["delivery_status"]: r for r in by_status}
    parts.append("<div class='card'><h2>Delivery reliability by zone</h2>" + _table(
        ["Zone", "Orders", "Late", "Failed", "Avg rating", "Cancels citing delivery"], zrows)
        + f"<p class='take'>A late delivery lowers the average rating from <b>{st['on_time']['avg_rating']}</b> to "
          f"<b>{st['late']['avg_rating']}</b>.</p></div>")

    # --- recommender -----------------------------------------------------
    parts.append(_recommender_section(conn))
    parts.append("<footer>Generated by <code>python -m mealsub report</code>. Synthetic data; see the README for the "
                 "planted effects and every metric definition.</footer></div></body></html>")
    return "".join(parts)


def _recommender_section(conn: sqlite3.Connection) -> str:
    val = R.validate(conn)
    days = val.get("planned_customer_days", 0)
    if not days:
        return ("<div class='card'><h2>Meal-plan recommender</h2><p class='note'>No plans generated yet. "
                "Run <code>python -m mealsub recommend --all</code>.</p></div>")
    out_band = val["calorie_days_outside_tolerance"]
    hard = sum(v for k, v in val.items() if k not in ("planned_customer_days", "calorie_days_outside_tolerance"))
    n_cust = conn.execute("SELECT COUNT(DISTINCT customer_id) FROM recommended_plans").fetchone()[0]
    week = conn.execute("SELECT MIN(plan_date) FROM recommended_plans").fetchone()[0]
    card = [f"<div class='card'><h2>Meal-plan recommender</h2><p class='note'>Weekly plans for the week of {esc(week)} "
            f"for every active subscriber. Hard rules (allergens, dislikes, slots, no repeats) are enforced in SQL and audited "
            f"by an independent query.</p><div class='kpis'>"
            + _kpi(f"{n_cust:,}", "customers planned") + _kpi(f"{days:,}", "customer-days planned")
            + _kpi(str(hard), "hard-rule violations")
            + _kpi(f"{100 * (days - out_band) / days:.2f}%", "days within &plusmn;10% of calorie target".replace("&plusmn;", "±"))
            + "</div>"]
    row = conn.execute(
        """SELECT c.customer_id FROM recommended_plans rp
           JOIN customers c ON c.customer_id = rp.customer_id
           JOIN customer_allergens ca ON ca.customer_id = c.customer_id
           JOIN customer_dislikes cd ON cd.customer_id = c.customer_id
           GROUP BY c.customer_id HAVING COUNT(DISTINCT rp.meal_type) >= 3
           ORDER BY c.customer_id LIMIT 1""").fetchone()
    if row:
        cid = row[0]
        c = conn.execute("SELECT * FROM customers WHERE customer_id=?", (cid,)).fetchone()
        alg = [r[0] for r in conn.execute("SELECT a.name FROM customer_allergens x JOIN allergens a USING(allergen_id) "
                                          "WHERE customer_id=?", (cid,))]
        dis = [r[0] for r in conn.execute("SELECT i.name FROM customer_dislikes x JOIN ingredients i USING(ingredient_id) "
                                          "WHERE customer_id=?", (cid,))]
        plan = R.plan_week(conn, cid, date.fromisoformat(week))
        rows = []
        for d in plan.days[:2]:
            for slot in R.SLOT_ORDER:
                if slot in d.meals:
                    m = d.meals[slot]
                    rows.append((f"{d.plan_date:%a %d %b}", slot, m.name, f"{m.calories:.0f}", f"{m.protein_g:.0f}"))
            rows.append((f"{d.plan_date:%a %d %b}", "<total>", "", f"{d.calories:.0f}", f"{d.protein_g:.0f}"))
        card.append(f"<h2 style='font-size:15px;margin-top:8px'>Example: customer #{cid}</h2>"
                    f"<p class='note'>Goal: {esc(c['goal'].replace('_', ' '))} &middot; target {c['daily_calorie_target']} kcal / "
                    f"{c['protein_target_g']} g protein &middot; allergens: <b>{esc(', '.join(alg))}</b> &middot; dislikes: "
                    f"<b>{esc(', '.join(dis))}</b></p>"
                    + _table(["Day", "Slot", "Meal", "kcal", "Protein g"], rows))
    card.append("</div>")
    return "".join(card)


def write_report(conn: sqlite3.Connection, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_report(conn), encoding="utf-8", newline="\n")
    return path
