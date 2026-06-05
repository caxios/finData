"""
Persist agent runs to:
  • backend/db/analysis.db   → analysis_runs table
  • backend/db/analyses/<TICKER>_<TS>.json   → full state dump
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_HERE)
_DB_DIR = os.path.join(_BACKEND_DIR, "db")
_ANALYSES_DIR = os.path.join(_DB_DIR, "analyses")
ANALYSIS_DB = os.path.join(_DB_DIR, "analysis.db")


def _ensure_dirs() -> None:
    os.makedirs(_DB_DIR, exist_ok=True)
    os.makedirs(_ANALYSES_DIR, exist_ok=True)


def _init_db() -> None:
    _ensure_dirs()
    conn = sqlite3.connect(ANALYSIS_DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_runs (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker           TEXT NOT NULL,
            run_at           TEXT NOT NULL,
            recommendation   TEXT NOT NULL,
            confidence       REAL,
            memo_markdown    TEXT,
            full_memo_json   TEXT,
            sub_reports_json TEXT
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_runs_ticker ON analysis_runs(ticker, run_at);"
    )
    conn.commit()
    conn.close()


def save_run(
    ticker: str,
    final_memo: dict[str, Any],
    sub_reports: dict[str, Any],
) -> tuple[str, int]:
    """
    Persist a single agent run.
    Returns (json_file_path, sqlite_row_id).
    """
    _init_db()
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d_%H%M%S")
    run_at_iso = now.isoformat(timespec="seconds")

    # ── JSON dump ──
    json_path = os.path.join(_ANALYSES_DIR, f"{ticker.upper()}_{ts}.json")
    payload = {
        "ticker": ticker,
        "run_at": run_at_iso,
        "final_memo": final_memo,
        "sub_reports": sub_reports,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    # ── SQLite row ──
    conn = sqlite3.connect(ANALYSIS_DB)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO analysis_runs
            (ticker, run_at, recommendation, confidence, memo_markdown,
             full_memo_json, sub_reports_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticker.upper(),
            run_at_iso,
            final_memo.get("recommendation", "UNKNOWN"),
            final_memo.get("confidence"),
            final_memo.get("memo_markdown"),
            json.dumps(final_memo, default=str),
            json.dumps(sub_reports, default=str),
        ),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()

    return json_path, row_id
