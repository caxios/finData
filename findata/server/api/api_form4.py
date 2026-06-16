import os
from findata.server.db.config import SEC_DB_DIR, ensure_parent_dir
import sqlite3
from typing import Optional, Union, List, Annotated
from fastapi import Query, HTTPException, APIRouter
from findata.sec.utils.form4.sec_form4_watchlist import (
    parse_all_form4_from_watchlist,
    parse_form4_for_ticker,
    WATCHLIST,
)
from findata.sec.utils.form4.form4_parser import parse_all_from_rss
from findata.server.db.form4_db import save_to_db


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_PATHS = {
    "watchlist": os.path.join(SEC_DB_DIR, "insider_watchlist.db"),
    "all":       os.path.join(SEC_DB_DIR, "insider_all.db"),
}
router = APIRouter(tags=["Form4"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _db_path(source: str) -> str:
    """Resolve source name to a database file path."""
    path = DB_PATHS.get(source)
    if not path:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source '{source}'. Use 'watchlist' or 'all'.",
        )
    return path


def _connect(source: str) -> sqlite3.Connection:
    """Open a connection with Row factory for dict-like access."""
    path = _db_path(source)
    ensure_parent_dir(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _tickers_missing_from_db(source: str, tickers: list) -> list:
    """Return the subset of `tickers` that have zero rows in the DB."""
    if not tickers:
        return []
    try:
        conn = _connect(source)
        try:
            present = {
                row[0]
                for row in conn.execute(
                    f"SELECT DISTINCT ticker FROM insider_trades "
                    f"WHERE ticker IN ({', '.join('?' * len(tickers))})",
                    tickers,
                ).fetchall()
            }
        finally:
            conn.close()
    except sqlite3.OperationalError:
        # Table or file doesn't exist yet — everything is missing.
        return list(tickers)
    return [t for t in tickers if t not in present]


def _db_has_any_rows(source: str) -> bool:
    try:
        conn = _connect(source)
        try:
            row = conn.execute(
                "SELECT 1 FROM insider_trades LIMIT 1"
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return False


def _lazy_load(source: str, tickers: list, count: int) -> None:
    """Populate the DB on demand for the requested scope.

    - If tickers are given, fetch + save only the ones with no rows yet.
    - Otherwise, if the table is empty/missing, run the per-source refresh.
    """
    db_path = _db_path(source)
    if tickers:
        missing = _tickers_missing_from_db(source, tickers)
        for t in missing:
            filings = parse_form4_for_ticker(t, count=count)
            if filings:
                save_to_db(filings, db_path)
        return

    if _db_has_any_rows(source):
        return
    if source == "watchlist":
        results = parse_all_form4_from_watchlist(count=count)
        all_filings = []
        for ticker_filings in results.values():
            all_filings.extend(ticker_filings)
    else:
        all_filings = parse_all_from_rss()
    if all_filings:
        save_to_db(all_filings, db_path)


# ---------------------------------------------------------------------------
# GET /api/trades — filtered + paginated trade list
# ---------------------------------------------------------------------------

@router.get("/api/trades")
def get_trades(
    source: Annotated[str, Query(description="DB source: 'watchlist' or 'all'")] = "watchlist",
    ticker: Optional[Union[str, List[str]]] = None,
    owner:  Optional[str] = None,
    code:   Optional[str] = None,
    acquired_or_disposed: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    min_value: Optional[float] = None,
    limit:  Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    auto_refresh: bool = True,
    count: Annotated[int, Query(ge=1, le=40, description="Filings per ticker to fetch on lazy-load")] = 5,
):
    """Return insider trades with optional filters and pagination.

    When `auto_refresh=True` (default) and the requested data is not yet in the
    local DB, this function will fetch + persist it on demand:
    - If `ticker` is given, any ticker with no rows in the DB is fetched via
      `parse_form4_for_ticker` (works for any ticker, not just WATCHLIST).
    - If `ticker` is None and the table is empty/missing, the per-source
      refresh path is used (RSS for `source='all'`, watchlist for
      `source='watchlist'`).
    Pass `auto_refresh=False` for the original read-only behavior.
    """
    if isinstance(ticker, str):
        tickers = [ticker.upper()]
    elif ticker:
        tickers = [t.upper() for t in ticker]
    else:
        tickers = []

    if auto_refresh:
        _lazy_load(source, tickers, count)

    conn = _connect(source)

    clauses = []
    params  = []

    if tickers:
        placeholders = ", ".join("?" * len(tickers))
        clauses.append(f"ticker IN ({placeholders})")
        params.extend(tickers)
    if owner:
        clauses.append("owner_name LIKE ?")
        params.append(f"%{owner}%")
    if code:
        clauses.append("transaction_code = ?")
        params.append(code.upper())
    if acquired_or_disposed:
        clauses.append("acquired_or_disposed = ?")
        params.append(acquired_or_disposed.upper())
    if date_from:
        clauses.append("transaction_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("transaction_date <= ?")
        params.append(date_to)
    if min_value is not None:
        clauses.append("transaction_value >= ?")
        params.append(min_value)

    where_sql = " AND ".join(clauses) if clauses else "1=1"

    # Total count (for pagination metadata)
    total = conn.execute(
        f"SELECT COUNT(*) FROM insider_trades WHERE {where_sql}", params
    ).fetchone()[0]

    # Page of data
    rows = conn.execute(
        f"""
        SELECT * FROM insider_trades
        WHERE  {where_sql}
        ORDER BY transaction_date DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    ).fetchall()

    conn.close()

    return {
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "trades": [dict(r) for r in rows],
    }


# ---------------------------------------------------------------------------
# GET /api/trades/{id} — single trade detail
# ---------------------------------------------------------------------------
@router.get("/api/trades/{trade_id}")
def get_trade(trade_id: int, source: str = Query("watchlist")):
    """Return the full detail of a single trade by its row ID."""
    conn = _connect(source)
    row = conn.execute(
        "SELECT * FROM insider_trades WHERE id = ?", (trade_id,)
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Trade not found")
    return dict(row)


# ---------------------------------------------------------------------------
# GET /api/summary — per-ticker aggregated stats
# ---------------------------------------------------------------------------
@router.get("/api/summary")
def get_summary(source: str = Query("watchlist")):
    """Aggregated overview per ticker (trade counts, values, insiders)."""
    conn = _connect(source)

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

    conn.close()
    return {"summary": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# GET /api/form4/rankings — top N tickers by net insider buying / selling
# ---------------------------------------------------------------------------
@router.get("/api/form4/rankings")
def get_rankings(
    source: str = Query("watchlist"),
    n: int = Query(10, ge=1, le=50, description="Top N per side"),
    ticker: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Top N tickers by net insider buying and net insider selling.

    Buy  = SUM(transaction_value) WHERE transaction_code = 'P'
    Sell = SUM(transaction_value) WHERE transaction_code = 'S'
    Net  = Buy - Sell

    When `ticker` is provided, returns a single aggregate object for that
    ticker instead of the top-N per-side lists.
    """
    conn = _connect(source)

    where = ["ticker IS NOT NULL", "ticker <> ''"]
    params: list = []
    if ticker:
        where.append("ticker = ?")
        params.append(ticker.upper())
    if date_from:
        where.append("transaction_date >= ?")
        params.append(date_from)
    if date_to:
        where.append("transaction_date <= ?")
        params.append(date_to)
    where_sql = " AND ".join(where)

    if ticker:
        conn.close()
        upper = ticker.upper()

        agg = {
            "ticker": upper,
            "issuer_name": None,
            "buy_value": 0.0,
            "sell_value": 0.0,
            "buy_count": 0,
            "sell_count": 0,
        }
        # Aggregate across BOTH watchlist and all DBs so the result matches the
        # union used by /api/company-data/{ticker}. Trades are deduped on
        # (source_url, owner_name, transaction_date, amount) — the same key as
        # company_data._select_form4_rows.
        seen: set[tuple] = set()
        for src_path in (DB_PATHS["all"], DB_PATHS["watchlist"]):
            if not os.path.exists(src_path):
                continue
            try:
                src_conn = sqlite3.connect(src_path)
                src_conn.row_factory = sqlite3.Row
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
            except sqlite3.Error:
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

    top_buy = conn.execute(
        f"SELECT *, (buy_value - sell_value) AS net_value "
        f"FROM ({base_sql}) WHERE (buy_value - sell_value) > 0 "
        f"ORDER BY net_value DESC LIMIT ?",
        params + [n],
    ).fetchall()

    top_sell = conn.execute(
        f"SELECT *, (buy_value - sell_value) AS net_value "
        f"FROM ({base_sql}) WHERE (buy_value - sell_value) < 0 "
        f"ORDER BY net_value ASC LIMIT ?",
        params + [n],
    ).fetchall()

    conn.close()
    return {
        "n": n,
        "top_net_buying":  [dict(r) for r in top_buy],
        "top_net_selling": [dict(r) for r in top_sell],
    }


# ---------------------------------------------------------------------------
# GET /api/watchlist — current tracked tickers
# ---------------------------------------------------------------------------
@router.get("/api/watchlist")
def get_watchlist():
    """Return the list of tickers from the watchlist config."""
    return {"watchlist": WATCHLIST}


# ---------------------------------------------------------------------------
# POST /api/refresh — manual scrape trigger
# ---------------------------------------------------------------------------
@router.post("/api/refresh")
def refresh(
    source: str = Query("watchlist"),
    count:  int = Query(5, ge=1, le=40, description="Filings per company (watchlist only)"),
):
    """
    Manually trigger a scrape cycle.

    - source=watchlist → scrape per-ticker from WATCHLIST (count configurable)
    - source=all       → scrape latest 100 Form 4s from SEC RSS feed
    """
    db_path = _db_path(source)

    if source == "watchlist":
        results = parse_all_form4_from_watchlist(count=count)
        all_filings = []
        for ticker_filings in results.values():
            all_filings.extend(ticker_filings)
    else:
        all_filings = parse_all_from_rss()

    inserted, skipped = save_to_db(all_filings, db_path)

    return {
        "status":   "ok",
        "source":   source,
        "inserted": inserted,
        "skipped":  skipped,
    }

