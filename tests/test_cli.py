"""The CLI and the HTML dashboard."""
from __future__ import annotations

import re

import pytest

from mealsub.cli import main
from mealsub.db import list_analytics
from mealsub.report import build_report

# the `db` fixture persists recommendations on the shared test database first
pytestmark = pytest.mark.usefixtures("db")


def run(db_path, *args):
    return main(["--db", str(db_path), *args])


def test_verify_exits_zero_on_clean_database(db_path, capsys):
    assert run(db_path, "verify") == 0
    out = capsys.readouterr().out
    assert "FAIL" not in out and out.count("OK") >= 14


def test_query_lists_and_runs(db_path, capsys):
    assert run(db_path, "query") == 0
    listing = capsys.readouterr().out
    for name in list_analytics():
        assert name in listing
    assert run(db_path, "query", "02", "--limit", "3") == 0
    out = capsys.readouterr().out
    assert "cohort" in out and "retention_pct" in out and "more rows" in out


def test_query_rejects_ambiguous_or_unknown_names(db_path):
    with pytest.raises(SystemExit):
        run(db_path, "query", "1")             # matches 10..14 and 01
    with pytest.raises(SystemExit):
        run(db_path, "query", "zzz")


def test_recommend_command(db_path, capsys):
    assert run(db_path, "recommend", "--all") == 0
    out = capsys.readouterr().out
    assert "allergen_in_plan" in out and "hard" not in out
    from mealsub import recommend as R
    from mealsub.db import connect
    conn = connect(db_path)
    cid = R.active_customers(conn)[0]
    conn.close()
    assert run(db_path, "recommend", "--customer", str(cid)) == 0
    assert "kcal" in capsys.readouterr().out


def test_missing_database_gives_a_helpful_message(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(["--db", str(tmp_path / "nope.db"), "verify"])
    assert "build" in str(exc.value)


def test_report_is_self_contained_html(db, tmp_path):
    html = build_report(db)
    assert html.startswith("<!doctype html>") and "</html>" in html
    assert "<svg" in html and "Cohort retention" in html and "Meal-plan recommender" in html
    assert not re.search(r"(src|href)=[\"']https?://", html), "report must not load external assets"
    assert "<script" not in html
    assert "None" not in re.sub(r"<[^>]+>", "", html), "a None leaked into the rendered page"
    out = tmp_path / "r.html"
    assert main(["--db", str(db.execute("PRAGMA database_list").fetchone()[2]), "report", "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")
