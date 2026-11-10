"""SQLite helpers: connections, schema setup and running the project's .sql files."""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"
ANALYTICS_DIR = SQL_DIR / "analytics"
RECOMMEND_DIR = SQL_DIR / "recommend"
DEFAULT_DB = ROOT / "data" / "mealsub.db"

MIN_SQLITE = (3, 35, 0)


def connect(path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    """Open a connection with foreign keys on and dict-like rows."""
    if sqlite3.sqlite_version_info < MIN_SQLITE:
        raise RuntimeError(
            f"SQLite {'.'.join(map(str, MIN_SQLITE))}+ required, found {sqlite3.sqlite_version}"
        )
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # SQRT() ships with SQLite >= 3.35 only when built with math functions.
    # Provide it if missing so analytics SQL runs on any Python build.
    try:
        conn.execute("SELECT sqrt(4.0)").fetchone()
    except sqlite3.OperationalError:
        conn.create_function("sqrt", 1, lambda x: None if x is None else math.sqrt(x),
                             deterministic=True)
    return conn


def init_schema(conn: sqlite3.Connection, triggers: bool = True) -> None:
    """Create tables and views (and, by default, the integrity triggers)."""
    conn.executescript((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))
    conn.executescript((SQL_DIR / "views.sql").read_text(encoding="utf-8"))
    if triggers:
        install_triggers(conn)
    conn.execute("PRAGMA foreign_keys = ON")


def install_triggers(conn: sqlite3.Connection) -> None:
    conn.executescript((SQL_DIR / "triggers.sql").read_text(encoding="utf-8"))


def verify(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """Run the integrity audit. Returns (check_name, violations) for every check."""
    rows = conn.execute(read_sql(SQL_DIR / "checks" / "integrity.sql")).fetchall()
    return [(r[0], r[1]) for r in rows]


def assert_valid(conn: sqlite3.Connection) -> None:
    failed = [(n, v) for n, v in verify(conn) if v]
    if failed:
        raise RuntimeError("integrity audit failed: " + ", ".join(f"{n}={v}" for n, v in failed))


def read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def query(conn: sqlite3.Connection, path: Path,
          params: Mapping[str, Any] | Sequence[Any] = ()) -> list[sqlite3.Row]:
    """Run a single-statement .sql file and return all rows."""
    return conn.execute(read_sql(path), params).fetchall()


def analytics(conn: sqlite3.Connection, name: str) -> list[sqlite3.Row]:
    """Run ``sql/analytics/<name>.sql``."""
    return query(conn, ANALYTICS_DIR / f"{name}.sql")


def list_analytics() -> list[str]:
    return sorted(p.stem for p in ANALYTICS_DIR.glob("*.sql"))


def as_of(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = 'as_of_date'").fetchone()
    if row is None:
        raise RuntimeError("database has no as_of_date; run `python -m mealsub build` first")
    return row[0]
