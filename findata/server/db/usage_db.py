"""
Usage database — event logging and monthly rollup for billing.

Tables live in the same ``accounts.db`` file alongside users/api_keys.
Uses WAL mode and atomic UPSERTs for concurrency safety.
"""

import sqlite3
from datetime import datetime, timezone

from findata.server.db import config as _config


def _db_path() -> str:
    return _config.ACCOUNTS_DB


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _current_period() -> str:
    """Return the current month as 'YYYY-MM'."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


# ── Schema ──────────────────────────────────────────────────────────

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS usage_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    endpoint    TEXT    NOT NULL,
    credits     INTEGER NOT NULL,
    status_code INTEGER NOT NULL,
    ts          TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_user_ts
    ON usage_events(user_id, ts);

CREATE TABLE IF NOT EXISTS usage_rollup (
    user_id     INTEGER NOT NULL,
    period      TEXT    NOT NULL,
    credits     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, period)
);
"""


def ensure_usage_schema(db_path: str | None = None) -> None:
    """Create usage tables if they don't exist.  Enables WAL mode."""
    path = db_path or _db_path()
    _config.ensure_parent_dir(path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA_SQL)
    conn.close()


# ── Write ───────────────────────────────────────────────────────────

def record_usage(
    user_id: int,
    endpoint: str,
    credits: int,
    status_code: int,
    *,
    db_path: str | None = None,
) -> None:
    """Record a usage event and atomically increment the monthly rollup.

    Both the INSERT and the UPSERT run in a single transaction so the
    rollup stays consistent with the event log.
    """
    path = db_path or _db_path()
    ensure_usage_schema(path)
    ts = _now_iso()
    period = _current_period()

    conn = sqlite3.connect(path)
    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            INSERT INTO usage_events (user_id, endpoint, credits, status_code, ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, endpoint, credits, status_code, ts),
        )
        conn.execute(
            """
            INSERT INTO usage_rollup (user_id, period, credits)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, period)
            DO UPDATE SET credits = credits + excluded.credits
            """,
            (user_id, period, credits),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


# ── Read ────────────────────────────────────────────────────────────

def get_month_credits(
    user_id: int,
    period: str | None = None,
    *,
    db_path: str | None = None,
) -> int:
    """Return total credits consumed by user for the given period.

    Uses the rollup table for fast O(1) reads.
    Falls back to 0 if no rollup row exists.
    """
    path = db_path or _db_path()
    ensure_usage_schema(path)
    period = period or _current_period()

    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT credits FROM usage_rollup WHERE user_id = ? AND period = ?",
            (user_id, period),
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def get_usage_summary(
    user_id: int,
    *,
    db_path: str | None = None,
) -> dict:
    """Return a usage summary for the current billing period."""
    path = db_path or _db_path()
    ensure_usage_schema(path)
    period = _current_period()

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        credits_used = get_month_credits(user_id, period, db_path=path)

        # Top endpoints by credit usage this period
        rows = conn.execute(
            """
            SELECT endpoint, SUM(credits) AS total_credits, COUNT(*) AS call_count
            FROM usage_events
            WHERE user_id = ? AND ts LIKE ?
            GROUP BY endpoint
            ORDER BY total_credits DESC
            LIMIT 20
            """,
            (user_id, f"{period}%"),
        ).fetchall()

        return {
            "period": period,
            "credits_used": credits_used,
            "endpoints": [dict(r) for r in rows],
        }
    finally:
        conn.close()
