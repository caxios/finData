"""
Search-driven company data: DB-first cache with conditional SEC scraping.

Layers on top of the existing watchlist pipelines without modifying them.
Reuses sec_10kq.db and insider_all.db as the cache; falls back to live SEC
fetches only when the cached data is missing or stale.
"""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

from findata.server.db.config import (
    INSIDER_ALL_DB,
    INSIDER_WATCHLIST_DB,
    SEC_10KQ_DB,
)
from findata.sec._cik import lookup_cik as _lib_lookup_cik
from findata.server.db.form4_db import save_to_db as save_form4_to_db
from findata.sec.utils.form4.form4_parser import parse_form4
from findata.sec.utils.form4.sec_form4_watchlist import fetch_filings as fetch_form4_filings
from findata.server.db.sec_10kq_db import save_batch as save_10kq_batch
from findata.sec.utils.sec_10kq.sec_10kq_parser import parse_single_filing
from findata.sec.utils.sec_10kq.sec_10kq_rss import fetch_and_resolve


# ── Freshness policy ────────────────────────────────────────────────────
# TTLs live in one place (findata.server.ingestion.freshness) so the read path
# and the schedulers can't drift apart (plan 06 §3.3).
from findata.server.ingestion.freshness import get_ttl_days as _get_ttl_days

TTL_10KQ_DAYS = _get_ttl_days("10kq")
TTL_FORM4_DAYS = _get_ttl_days("form4")

# Default 10-K/Q rows to surface in a response (caller can override).
# A staleness re-scrape always pulls at least this many.
SCRAPE_COUNT_10KQ = 5
SCRAPE_COUNT_FORM4 = 10

DEFAULT_LIMIT_10KQ = 4
RETURN_LIMIT_FORM4 = 30


# ── Typed errors so the FastAPI layer can map to HTTP statuses ──────────
class TickerNotFound(Exception):
    """Raised when a ticker cannot be resolved to a CIK."""


class SECRateLimit(Exception):
    """Raised when SEC returns 403 or 429 during a scrape."""

    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after


# ── Helpers ─────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _is_within_ttl(latest_date: str | None, ttl_days: int) -> bool:
    parsed = _parse_date(latest_date)
    if parsed is None:
        return False
    return parsed >= datetime.utcnow() - timedelta(days=ttl_days)


def resolve_ticker(ticker: str) -> tuple[str, str]:
    """Ticker → (zero-padded CIK, entity_name). Raises TickerNotFound on miss."""
    cik, name = _lib_lookup_cik(ticker)
    if not cik:
        raise TickerNotFound(f"Unknown ticker {ticker.upper()}")
    return cik.zfill(10), name or ticker.upper()


# ── 10-K / 10-Q DB layer ────────────────────────────────────────────────
def _select_10kq_rows(cik: str, limit: int = DEFAULT_LIMIT_10KQ) -> list[dict[str, Any]]:
    if not os.path.exists(SEC_10KQ_DB):
        return []
    cik_unpadded = cik.lstrip("0")
    conn = sqlite3.connect(SEC_10KQ_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT accession_number, form_type, filing_date, company_name,
               index_url, document_url,
               (business IS NOT NULL AND length(business) > 0)         AS has_business,
               (risk_factors IS NOT NULL AND length(risk_factors) > 0) AS has_risk_factors,
               (mda IS NOT NULL AND length(mda) > 0)                   AS has_mda
          FROM filing_sections
         WHERE cik IN (?, ?)
         ORDER BY filing_date DESC
         LIMIT ?
        """,
        (cik, cik_unpadded, limit),
    ).fetchall()
    conn.close()
    return [
        {**dict(r), "has_business": bool(r["has_business"]),
         "has_risk_factors": bool(r["has_risk_factors"]),
         "has_mda": bool(r["has_mda"])}
        for r in rows
    ]


def _latest_10kq_date(cik: str) -> str | None:
    rows = _select_10kq_rows(cik, limit=1)
    return rows[0]["filing_date"] if rows else None


def _count_10kq_rows(cik: str) -> int:
    """Number of 10-K/10-Q rows already cached for `cik` (padded or unpadded)."""
    if not os.path.exists(SEC_10KQ_DB):
        return 0
    cik_unpadded = cik.lstrip("0")
    conn = sqlite3.connect(SEC_10KQ_DB)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM filing_sections WHERE cik IN (?, ?)",
            (cik, cik_unpadded),
        ).fetchone()
    finally:
        conn.close()
    return int(row[0]) if row else 0


# ── Form 4 DB layer ─────────────────────────────────────────────────────
_FORM4_SELECT_SQL = """
    SELECT owner_name, officer_title,
           is_director, is_officer, is_ten_pct_owner,
           transaction_date, transaction_code,
           security_title, security_category,
           amount, acquired_or_disposed,
           price_per_share, shares_owned_after,
           trade_ratio_pct, transaction_value, market_value_after,
           source_url
      FROM insider_trades
     WHERE UPPER(ticker)        = ?
        OR UPPER(issuer_symbol) = ?
        OR issuer_cik           = ?
        OR issuer_cik           = ?
     ORDER BY transaction_date DESC
     LIMIT ?
"""


def _select_form4_rows(ticker: str, cik: str, limit: int = RETURN_LIMIT_FORM4) -> list[dict[str, Any]]:
    cik_padded = cik.zfill(10)
    cik_unpadded = cik.lstrip("0")
    rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str, float | None]] = set()

    for path in (INSIDER_ALL_DB, INSIDER_WATCHLIST_DB):
        if not os.path.exists(path):
            continue
        try:
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            for r in conn.execute(
                _FORM4_SELECT_SQL,
                (ticker.upper(), ticker.upper(), cik_padded, cik_unpadded, limit),
            ).fetchall():
                key = (
                    r["source_url"] or "",
                    r["owner_name"] or "",
                    r["transaction_date"] or "",
                    r["amount"],
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                rows.append(dict(r))
            conn.close()
        except sqlite3.Error:
            continue

    rows.sort(key=lambda r: r.get("transaction_date") or "", reverse=True)
    return rows[:limit]


def _latest_form4_date(ticker: str, cik: str) -> str | None:
    rows = _select_form4_rows(ticker, cik, limit=1)
    return rows[0]["transaction_date"] if rows else None


# ── Scraper wrappers (with rate-limit translation) ──────────────────────
def _wrap_rate_limit(exc: Exception) -> SECRateLimit | None:
    """Return a SECRateLimit if exc is a 403/429, else None."""
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        if status in (403, 429):
            retry_after = exc.response.headers.get("Retry-After")
            try:
                ra = int(retry_after) if retry_after else 60
            except ValueError:
                ra = 60
            return SECRateLimit(f"SEC returned {status}", retry_after=ra)
    return None


def _scrape_10kq(cik: str, count: int = SCRAPE_COUNT_10KQ, include_archive: bool = False) -> int:
    """Fetch + parse + save 10-K/10-Q filings for `cik`. Returns inserted count."""
    try:
        filings = fetch_and_resolve(cik, count=count, include_archive=include_archive)
    except requests.HTTPError as e:
        rate = _wrap_rate_limit(e)
        if rate:
            raise rate from e
        raise
    if not filings:
        return 0

    parsed: list[dict] = []
    for filing in filings:
        try:
            parsed.append(parse_single_filing(filing))
        except requests.HTTPError as e:
            rate = _wrap_rate_limit(e)
            if rate:
                raise rate from e
            print(f"  [WARN] parse_single_filing failed for {filing.get('accession_number')}: {e}")
        except Exception as e:
            print(f"  [WARN] parse_single_filing failed for {filing.get('accession_number')}: {e}")
        time.sleep(0.2)

    inserted, _ = save_10kq_batch(parsed, SEC_10KQ_DB)
    return inserted


def _scrape_form4(cik: str) -> int:
    """
    Fetch + parse + save recent Form 4 filings for the company at `cik`.
    Returns inserted count. EDGAR's filing feed is keyed by CIK, not ticker.
    """
    try:
        filings = fetch_form4_filings(cik, count=SCRAPE_COUNT_FORM4)
    except requests.HTTPError as e:
        rate = _wrap_rate_limit(e)
        if rate:
            raise rate from e
        raise

    parsed: list[dict] = []
    for item in filings:
        link = item.get("link")
        if not link:
            continue
        try:
            row = parse_form4(link)
            row["rss_meta"] = {
                "title": item.get("title"),
                "form_type": item.get("form_type"),
                "updated": item.get("updated"),
            }
            parsed.append(row)
        except requests.HTTPError as e:
            rate = _wrap_rate_limit(e)
            if rate:
                raise rate from e
            print(f"  [WARN] parse_form4 failed for {link}: {e}")
        except Exception as e:
            print(f"  [WARN] parse_form4 failed for {link}: {e}")
        time.sleep(0.2)

    if not parsed:
        return 0
    inserted, _ = save_form4_to_db(parsed, INSIDER_ALL_DB)
    return inserted


# ── Public orchestrator ─────────────────────────────────────────────────
def get_company_data(
    ticker: str,
    limit_10kq: int = DEFAULT_LIMIT_10KQ,
    limit_form4: int = RETURN_LIMIT_FORM4,
    include_archive: bool = False,
) -> dict[str, Any]:
    """
    Resolve ticker → CIK, then return cached 10-K/10-Q + Form 4 data.

    Re-scrapes when:
      • the cache is stale per TTL, OR
      • the DB has fewer 10-K/Q rows than the caller asked for.

    `limit_10kq` controls how many filings to surface AND, on a miss, how
    many to pull from EDGAR's RSS. Pass a large number (e.g. 1000) for
    "all available".

    Raises:
        TickerNotFound: ticker cannot be mapped to a CIK.
        SECRateLimit:   SEC returned 403/429 during a fallback fetch.
    """
    ticker = ticker.upper().strip()
    cik, company_name = resolve_ticker(ticker)

    have_10kq = _count_10kq_rows(cik)
    fresh_10kq = _is_within_ttl(_latest_10kq_date(cik), TTL_10KQ_DAYS)
    enough_10kq = have_10kq >= limit_10kq
    served_10kq_from_cache = fresh_10kq and enough_10kq

    fresh_form4 = _is_within_ttl(_latest_form4_date(ticker, cik), TTL_FORM4_DAYS)

    if not served_10kq_from_cache or include_archive:
        # Pull at least `limit_10kq` from EDGAR so we can satisfy the
        # request after one round-trip; save_batch dedupes against
        # what's already in the DB via UNIQUE(accession_number).
        # `include_archive=True` always forces a scrape so the user
        # actually gets the older filings they asked for.
        _scrape_10kq(
            cik,
            count=max(limit_10kq, SCRAPE_COUNT_10KQ),
            include_archive=include_archive,
        )
    if not fresh_form4:
        _scrape_form4(cik)

    if served_10kq_from_cache and fresh_form4:
        cache_status = "hit"
    elif served_10kq_from_cache or fresh_form4:
        cache_status = "partial"
    else:
        cache_status = "miss"

    return {
        "ticker": ticker,
        "cik": cik,
        "company_name": company_name,
        "cache_status": cache_status,
        "filings_10kq": _select_10kq_rows(cik, limit=limit_10kq),
        "form4_trades": _select_form4_rows(ticker, cik, limit=limit_form4),
        "fetched_at": _now_iso(),
    }
