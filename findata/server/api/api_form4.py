import os
import threading
from datetime import datetime, timezone
from findata.server.db.config import SEC_DB_DIR
from typing import Optional, List, Annotated
from fastapi import Query, HTTPException, APIRouter, Request
from findata.sec.utils.form4.sec_form4_watchlist import (
    parse_all_form4_from_watchlist,
    parse_form4_for_ticker,
    WATCHLIST,
)
from findata.sec.utils.form4.form4_parser import parse_all_from_rss
from findata.sec.utils.form4.form4_submissions import (
    fetch_form4_by_period,
    TickerNotFound,
)
from findata.server.db.form4_db import (
    save_to_db,
    is_covered,
    record_coverage,
)
from findata.server.db import form4_repo
from findata.server.billing.costs import LAZY_FETCH_CREDITS


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


# Single-flight: serialize identical concurrent fetches so 10 users asking for
# the same uncached (ticker, period) trigger ONE upstream fetch, not ten.
_inflight_lock = threading.Lock()
_inflight: dict = {}


def _flight_lock(key: tuple) -> threading.Lock:
    with _inflight_lock:
        lk = _inflight.get(key)
        if lk is None:
            lk = threading.Lock()
            _inflight[key] = lk
        return lk


def _lazy_load(
    source: str,
    tickers: list,
    count: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> int:
    """Populate the DB on demand for the requested scope.

    - Tickers + a date range → historical backfill via submissions JSON, gated
      by per-(ticker, window) coverage so each window is fetched at most once.
    - Tickers, no date range → fetch recent N for any ticker with no rows yet.
    - No tickers → if the table is empty/missing, run the per-source refresh.

    Returns the number of upstream fetch operations performed (used to bill the
    cache-miss as a higher-credit event — plan 05 §3.3).

    Raises HTTPException(422) if a requested ticker can't be resolved to a CIK.
    """
    db_path = _db_path(source)
    fetches = 0

    if tickers:
        # ── Historical / period-aware backfill ──────────────────────
        if date_from or date_to:
            lo = date_from or "0001-01-01"
            hi = date_to or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for t in tickers:
                if is_covered(db_path, t, lo, hi):
                    continue
                lock = _flight_lock((db_path, t, lo, hi))
                with lock:
                    # Double-check inside the lock: a concurrent request may
                    # have just recorded coverage while we waited.
                    if is_covered(db_path, t, lo, hi):
                        continue
                    try:
                        filings = fetch_form4_by_period(t, lo, hi)
                    except TickerNotFound:
                        raise HTTPException(
                            status_code=422,
                            detail={
                                "error": {
                                    "code": "INVALID_TICKER",
                                    "message": f"Unknown ticker: {t!r}",
                                }
                            },
                        )
                    if filings:
                        save_to_db(filings, db_path)
                    # Record coverage even when empty: the window IS now known
                    # (the company simply had no Form 4s then), so don't refetch.
                    record_coverage(db_path, t, lo, hi)
                    fetches += 1
            return fetches

        # ── Recent-N (no date range) ────────────────────────────────
        missing = form4_repo.tickers_missing(db_path, tickers)
        for t in missing:
            filings = parse_form4_for_ticker(t, count=count)
            if filings:
                save_to_db(filings, db_path)
            fetches += 1
        return fetches

    # ── No tickers: per-source bulk refresh if empty ────────────────
    if form4_repo.has_any_rows(db_path):
        return 0
    if source == "watchlist":
        results = parse_all_form4_from_watchlist(count=count)
        all_filings = []
        for ticker_filings in results.values():
            all_filings.extend(ticker_filings)
    else:
        all_filings = parse_all_from_rss()
    if all_filings:
        save_to_db(all_filings, db_path)
    return 1


# ---------------------------------------------------------------------------
# GET /api/trades — filtered + paginated trade list
# ---------------------------------------------------------------------------

@router.get("/api/trades")
def get_trades(
    request: Request,
    source: Annotated[str, Query(description="DB source: 'watchlist' or 'all'")] = "watchlist",
    ticker: Annotated[Optional[List[str]], Query(description="One or more tickers (repeat the param for multiple)")] = None,
    owner:  Optional[str] = None,
    code:   Optional[str] = None,
    acquired_or_disposed: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    min_value: Optional[float] = None,
    limit:  Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    auto_refresh: bool = True,
    count: Annotated[int, Query(ge=1, le=100, description="Filings per ticker to fetch on lazy-load")] = 5,
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
    tickers = [t.upper() for t in ticker] if ticker else []

    if auto_refresh:
        fetches = _lazy_load(source, tickers, count, date_from, date_to)
        # Bill a cache-miss/backfill as a higher-credit event (plan 05 §3.3).
        # The metering middleware reads request.state.extra_credits.
        if fetches:
            request.state.extra_credits = fetches * LAZY_FETCH_CREDITS

    total, trades = form4_repo.query_trades(
        _db_path(source),
        tickers=tickers,
        owner=owner,
        code=code,
        acquired_or_disposed=acquired_or_disposed,
        date_from=date_from,
        date_to=date_to,
        min_value=min_value,
        limit=limit,
        offset=offset,
    )

    return {
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "trades": trades,
    }


# ---------------------------------------------------------------------------
# GET /api/trades/{id} — single trade detail
# ---------------------------------------------------------------------------
@router.get("/api/trades/{trade_id}")
def get_trade(trade_id: int, source: str = Query("watchlist")):
    """Return the full detail of a single trade by its row ID."""
    row = form4_repo.get_trade(_db_path(source), trade_id)
    if not row:
        raise HTTPException(status_code=404, detail="Trade not found")
    return row


# ---------------------------------------------------------------------------
# GET /api/summary — per-ticker aggregated stats
# ---------------------------------------------------------------------------
@router.get("/api/summary")
def get_summary(source: str = Query("watchlist")):
    """Aggregated overview per ticker (trade counts, values, insiders)."""
    return {"summary": form4_repo.summary(_db_path(source))}


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
    if ticker:
        # Aggregate across BOTH watchlist and all DBs so the result matches the
        # union used by /api/company-data/{ticker}.
        return form4_repo.rankings_for_ticker(
            [DB_PATHS["all"], DB_PATHS["watchlist"]],
            ticker, date_from, date_to,
        )

    top_buy, top_sell = form4_repo.top_rankings(
        _db_path(source), n=n, date_from=date_from, date_to=date_to,
    )
    return {
        "n": n,
        "top_net_buying":  top_buy,
        "top_net_selling": top_sell,
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

