"""
Upstream cost measurement — Track 0 of plan 03 (Billing & Margin Pricing).

The two paid-upstream endpoints incur a *real* per-call cost:
- ``/api/transcript``     → Tavily search + extract calls
- ``/api/filings/chat``   → Google GenAI (Gemini) tokens, multi-agent

This module is the single source of truth for **how much those calls cost
us in dollars**.  It provides:

1. Tunable provider unit-prices (update with real invoices).
2. Cost estimators (``tavily_transcript_usd``, ``llm_cost_usd``).
3. A ``upstream_cost_events`` table + recorders to log actual spend.
4. Period summaries (``get_month_upstream_usd``, ``get_upstream_cost_summary``)
   used by the cost guardrail (09 §3.5) and to derive credit weights:
   set ``billing/costs.py`` credits so that
   ``plans.credits_to_usd(credits) >= plans.price_with_margin(avg_cost)``.

Layering note: recording cost is a *server* concern (it persists to disk),
so instrumentation lives in the server endpoints, not the pure library
functions that make the upstream calls.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from findata.server.db import config as _config


# =====================================================================
# Provider unit prices (TUNABLE — replace with figures from real invoices)
# =====================================================================

# ── Tavily ──────────────────────────────────────────────────────────
# A transcript fetch does one advanced *search* then one or more advanced
# *extract* calls until a usable page is found.
TAVILY_SEARCH_USD: float = 0.008          # one advanced search
TAVILY_EXTRACT_USD: float = 0.008         # one advanced extract (per URL)
AVG_TRANSCRIPT_EXTRACTS: int = 2          # avg extract attempts per fetch

# ── Google GenAI (Gemini) ───────────────────────────────────────────
# Per-1M-token prices.  Keep keys in sync with ``sec/agents/llm.py``
# (default model: gemini-2.5-pro).
LLM_PRICING_USD_PER_1M: dict[str, tuple[float, float]] = {
    # model: (input_per_1M, output_per_1M)
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.30, 2.50),
}
DEFAULT_LLM_MODEL = "gemini-2.5-pro"

# Rough average tokens per CIO chat turn (multi-agent: CIO + sub-analysts).
# This is an ESTIMATE used until precise token capture is wired through an
# LLM callback (see ``record_chat_cost`` — pass real token counts to override).
EST_CHAT_INPUT_TOKENS: int = 8_000
EST_CHAT_OUTPUT_TOKENS: int = 1_200


# =====================================================================
# Cost estimators
# =====================================================================

def tavily_transcript_usd(n_extracts: int = AVG_TRANSCRIPT_EXTRACTS) -> float:
    """Estimated USD cost of one transcript fetch (1 search + N extracts)."""
    return round(TAVILY_SEARCH_USD + n_extracts * TAVILY_EXTRACT_USD, 6)


def llm_cost_usd(
    input_tokens: int,
    output_tokens: int,
    model: str = DEFAULT_LLM_MODEL,
) -> float:
    """USD cost for a given token usage on a given model."""
    in_per_1m, out_per_1m = LLM_PRICING_USD_PER_1M.get(
        model, LLM_PRICING_USD_PER_1M[DEFAULT_LLM_MODEL]
    )
    cost = (input_tokens / 1_000_000) * in_per_1m + (
        output_tokens / 1_000_000
    ) * out_per_1m
    return round(cost, 6)


def estimate_chat_usd(model: str = DEFAULT_LLM_MODEL) -> float:
    """Estimated USD cost of one CIO chat turn (using average token counts)."""
    return llm_cost_usd(EST_CHAT_INPUT_TOKENS, EST_CHAT_OUTPUT_TOKENS, model)


# =====================================================================
# Persistence
# =====================================================================

def _db_path(db_path: str | None = None) -> str:
    return db_path if db_path is not None else _config.ACCOUNTS_DB


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _current_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS upstream_cost_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,                       -- may be NULL (unattributed)
    endpoint    TEXT    NOT NULL,
    provider    TEXT    NOT NULL,              -- 'tavily' | 'google_genai'
    detail      TEXT,                          -- JSON: units (searches/extracts/tokens)
    usd_cost    REAL    NOT NULL,
    estimated   INTEGER NOT NULL DEFAULT 1,    -- 1 = estimated, 0 = measured
    ts          TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_upstream_ts ON upstream_cost_events(ts);
CREATE INDEX IF NOT EXISTS idx_upstream_user_ts ON upstream_cost_events(user_id, ts);
"""


def ensure_upstream_schema(db_path: str | None = None) -> None:
    """Create the upstream_cost_events table if it doesn't exist (WAL mode)."""
    path = _db_path(db_path)
    _config.ensure_parent_dir(path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA_SQL)
    conn.close()


def record_upstream_cost(
    endpoint: str,
    provider: str,
    usd_cost: float,
    *,
    user_id: Optional[int] = None,
    detail: Optional[dict] = None,
    estimated: bool = True,
    db_path: str | None = None,
) -> None:
    """Persist a single upstream cost event."""
    path = _db_path(db_path)
    ensure_upstream_schema(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            INSERT INTO upstream_cost_events
                (user_id, endpoint, provider, detail, usd_cost, estimated, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                endpoint,
                provider,
                json.dumps(detail) if detail is not None else None,
                float(usd_cost),
                1 if estimated else 0,
                _now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ── Convenience recorders for the two paid endpoints ────────────────

def record_transcript_cost(
    *,
    user_id: Optional[int] = None,
    endpoint: str = "/api/transcript",
    n_extracts: int = AVG_TRANSCRIPT_EXTRACTS,
    db_path: str | None = None,
) -> float:
    """Record the (estimated) Tavily cost of one transcript fetch. Returns the cost."""
    cost = tavily_transcript_usd(n_extracts)
    record_upstream_cost(
        endpoint,
        "tavily",
        cost,
        user_id=user_id,
        detail={"searches": 1, "extracts": n_extracts},
        estimated=True,
        db_path=db_path,
    )
    return cost


def record_chat_cost(
    *,
    user_id: Optional[int] = None,
    endpoint: str = "/api/filings/chat",
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    model: str = DEFAULT_LLM_MODEL,
    db_path: str | None = None,
) -> float:
    """Record the LLM cost of one chat turn.

    If real ``input_tokens``/``output_tokens`` are supplied (e.g. from an
    LLM callback) the cost is *measured*; otherwise an average-based
    *estimate* is recorded.  Returns the cost.
    """
    if input_tokens is not None and output_tokens is not None:
        cost = llm_cost_usd(input_tokens, output_tokens, model)
        estimated = False
        detail = {"input_tokens": input_tokens, "output_tokens": output_tokens, "model": model}
    else:
        cost = estimate_chat_usd(model)
        estimated = True
        detail = {
            "input_tokens": EST_CHAT_INPUT_TOKENS,
            "output_tokens": EST_CHAT_OUTPUT_TOKENS,
            "model": model,
            "estimate": True,
        }
    record_upstream_cost(
        endpoint,
        "google_genai",
        cost,
        user_id=user_id,
        detail=detail,
        estimated=estimated,
        db_path=db_path,
    )
    return cost


# =====================================================================
# Summaries (used by the guardrail and to derive credit weights)
# =====================================================================

def get_month_upstream_usd(
    period: str | None = None,
    *,
    db_path: str | None = None,
) -> float:
    """Total upstream USD spend across all users for the given month."""
    path = _db_path(db_path)
    ensure_upstream_schema(path)
    period = period or _current_period()
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(usd_cost), 0) FROM upstream_cost_events WHERE ts LIKE ?",
            (f"{period}%",),
        ).fetchone()
        return round(row[0] or 0.0, 6)
    finally:
        conn.close()


def get_upstream_cost_summary(
    period: str | None = None,
    *,
    db_path: str | None = None,
) -> dict:
    """Per-endpoint cost breakdown + average cost per call for the period.

    This is the Track 0 output you use to calibrate credit weights:
    for each paid endpoint, ``avg_usd_per_call`` is the real cost to cover.
    """
    path = _db_path(db_path)
    ensure_upstream_schema(path)
    period = period or _current_period()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                endpoint,
                provider,
                COUNT(*)            AS calls,
                SUM(usd_cost)       AS total_usd,
                AVG(usd_cost)       AS avg_usd_per_call
            FROM upstream_cost_events
            WHERE ts LIKE ?
            GROUP BY endpoint, provider
            ORDER BY total_usd DESC
            """,
            (f"{period}%",),
        ).fetchall()
        endpoints = [
            {
                "endpoint": r["endpoint"],
                "provider": r["provider"],
                "calls": r["calls"],
                "total_usd": round(r["total_usd"] or 0.0, 6),
                "avg_usd_per_call": round(r["avg_usd_per_call"] or 0.0, 6),
            }
            for r in rows
        ]
        return {
            "period": period,
            "total_usd": round(sum(e["total_usd"] for e in endpoints), 6),
            "endpoints": endpoints,
        }
    finally:
        conn.close()
