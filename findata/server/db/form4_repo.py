"""
Form 4 read-path repository (plan 07 Step 1).

All the SQL that used to live inline in ``api/api_form4.py`` now lives here, so
the router is thin and the dialect-specific bits are localized to one module
(the migration seam). Connections are opened via ``engine.connect`` rather than
raw ``sqlite3`` calls. SQL is unchanged from the original router — behavior is
identical on SQLite.
"""

from __future__ import annotations

import os
from findata.server.db.engine import connect
import psycopg2
import psycopg2.extras
from typing import Any

from findata.server.db.engine import connect


# ── Presence / coverage checks ──────────────────────────────────────

def tickers_missing(db_path: str, tickers: list[str]) -> list[str]:
    """Return the subset of ``tickers`` that have zero rows in the DB."""
    if not tickers:
        return []
    try:
        conn = connect(db_path)
        try:
            present = {
                row[0]
                for row in conn.execute(
                    f"SELECT DISTINCT ticker FROM insider_trades "
                    f"WHERE ticker IN ({', '.join('%s' * len(tickers))})",
                    tickers,
                ).fetchall()
            }
        finally:
            conn.close()
    except psycopg2.OperationalError:
        # Table or file doesn't exist yet — everything is missing.
        return list(tickers)
    return [t for t in tickers if t not in present]


def has_any_rows(db_path: str) -> bool:
    """True if the insider_trades table has at least one row."""
    try:
        conn = connect(db_path)
        try:
            row = conn.execute("SELECT 1 FROM insider_trades LIMIT 1").fetchone()
            return row is not None
        finally:
            conn.close()
    except psycopg2.OperationalError:
        return False


# ── Trade queries ───────────────────────────────────────────────────

def query_trades(
    db_path: str,
    *,
    tickers: list[str] | None = None,
    owner: str | None = None,
    code: str | None = None,
    acquired_or_disposed: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_value: float | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[dict[str, Any]]]:
    """Return (total_matching, page_of_rows) for the given filters."""
    clauses: list[str] = []
    params: list[Any] = []

    if tickers:
        placeholders = ", ".join("%s" * len(tickers))
        clauses.append(f"ticker IN ({placeholders})")
        params.extend(tickers)
    if owner:
        clauses.append("owner_name LIKE %s")
        params.append(f"%{owner}%")
    if code:
        clauses.append("transaction_code = %s")
        params.append(code.upper())
    if acquired_or_disposed:
        clauses.append("acquired_or_disposed = %s")
        params.append(acquired_or_disposed.upper())
    if date_from:
        clauses.append("transaction_date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("transaction_date <= %s")
        params.append(date_to)
    if min_value is not None:
        clauses.append("transaction_value >= %s")
        params.append(min_value)

    where_sql = " AND ".join(clauses) if clauses else "1=1"

    conn = connect(db_path)
    try:
        total = conn.execute(
            f"SELECT COUNT(*) FROM insider_trades WHERE {where_sql}", params
        ).fetchone()[0]

        rows = conn.execute(
            f"""
            SELECT * FROM insider_trades
            WHERE  {where_sql}
            ORDER BY transaction_date DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        ).fetchall()
    finally:
        conn.close()

    return total, [dict(r) for r in rows]


def get_trade(db_path: str, trade_id: int) -> dict[str, Any] | None:
    """Return a single trade row by id, or None."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM insider_trades WHERE id = %s", (trade_id,)
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def summary(db_path: str) -> list[dict[str, Any]]:
    """Per-ticker aggregated stats (counts, buy/sell values, insiders)."""
    conn = connect(db_path)
    try:
        rows = conn.execute("""
            SELECT
                ticker,
                COUNT(*)
                    AS total_trades,
                SUM(CASE WHEN acquired_or_disposed = 'A' THEN 1 ELSE 0 END)
                    AS total_buys,
                SUM(CASE WHEN acquired_or_disposed = 'D' THEN 1 ELSE 0 END)
                    AS total_sells,
                SUM(CASE WHEN acquired_or_disposed = 'A'
                          THEN COALESCE(transaction_value, 0) ELSE 0 END)
                    AS total_buy_value,
                SUM(CASE WHEN acquired_or_disposed = 'D'
                          THEN COALESCE(transaction_value, 0) ELSE 0 END)
                    AS total_sell_value,
                MAX(transaction_date)
                    AS latest_trade_date,
                COUNT(DISTINCT owner_name)
                    AS unique_insiders
            FROM insider_trades
            GROUP BY ticker
            ORDER BY ticker
        """).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# ── Rankings ────────────────────────────────────────────────────────

def _rankings_where(ticker: str | None, date_from: str | None,
                    date_to: str | None) -> tuple[str, list[Any]]:
    where = ["ticker IS NOT NULL", "ticker <> ''"]
    params: list[Any] = []
    if ticker:
        where.append("ticker = %s")
        params.append(ticker.upper())
    if date_from:
        where.append("transaction_date >= %s")
        params.append(date_from)
    if date_to:
        where.append("transaction_date <= %s")
        params.append(date_to)
    return " AND ".join(where), params


def rankings_for_ticker(
    db_paths: list[str],
    ticker: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Aggregate buy/sell for a single ticker across multiple DB files.

    Trades are deduped on (source_url, owner_name, transaction_date, amount) —
    the same key used by company_data._select_form4_rows.
    """
    where_sql, params = _rankings_where(ticker, date_from, date_to)
    upper = ticker.upper()
    agg: dict[str, Any] = {
        "ticker": upper,
        "issuer_name": None,
        "buy_value": 0.0,
        "sell_value": 0.0,
        "buy_count": 0,
        "sell_count": 0,
    }
    seen: set[tuple] = set()
    for src_path in db_paths:
        if not os.path.exists(src_path):
            continue
        try:
            src_conn = connect(src_path)
            rows = src_conn.execute(
                f"""
                SELECT issuer_name, transaction_code, transaction_value,
                       source_url, owner_name, transaction_date, amount
                  FROM insider_trades
                 WHERE {where_sql}
                """,
                params,
            ).fetchall()
            src_conn.close()
        except psycopg2.Error:
            continue

        for r in rows:
            key = (
                r["source_url"] or "",
                r["owner_name"] or "",
                r["transaction_date"] or "",
                r["amount"],
            )
            if key in seen:
                continue
            seen.add(key)
            if agg["issuer_name"] is None and r["issuer_name"]:
                agg["issuer_name"] = r["issuer_name"]
            value = r["transaction_value"] or 0
            if r["transaction_code"] == "P":
                agg["buy_value"] += value
                agg["buy_count"] += 1
            elif r["transaction_code"] == "S":
                agg["sell_value"] += value
                agg["sell_count"] += 1

    agg["net_value"] = agg["buy_value"] - agg["sell_value"]
    return agg


def top_rankings(
    db_path: str,
    n: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Top-N tickers by net buying and net selling. Returns (top_buy, top_sell)."""
    where_sql, params = _rankings_where(None, date_from, date_to)

    base_sql = f"""
        SELECT
            ticker,
            MAX(issuer_name) AS issuer_name,
            SUM(CASE WHEN transaction_code = 'P'
                     THEN COALESCE(transaction_value, 0) ELSE 0 END) AS buy_value,
            SUM(CASE WHEN transaction_code = 'S'
                     THEN COALESCE(transaction_value, 0) ELSE 0 END) AS sell_value,
            SUM(CASE WHEN transaction_code = 'P' THEN 1 ELSE 0 END) AS buy_count,
            SUM(CASE WHEN transaction_code = 'S' THEN 1 ELSE 0 END) AS sell_count
        FROM insider_trades
        WHERE {where_sql}
        GROUP BY ticker
        HAVING buy_value > 0 OR sell_value > 0
    """

    conn = connect(db_path)
    try:
        top_buy = conn.execute(
            f"SELECT *, (buy_value - sell_value) AS net_value "
            f"FROM ({base_sql}) WHERE (buy_value - sell_value) > 0 "
            f"ORDER BY net_value DESC LIMIT %s",
            params + [n],
        ).fetchall()

        top_sell = conn.execute(
            f"SELECT *, (buy_value - sell_value) AS net_value "
            f"FROM ({base_sql}) WHERE (buy_value - sell_value) < 0 "
            f"ORDER BY net_value ASC LIMIT %s",
            params + [n],
        ).fetchall()
    finally:
        conn.close()

    return [dict(r) for r in top_buy], [dict(r) for r in top_sell]
