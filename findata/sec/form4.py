"""
Form 4 insider trades — library layer.

Fetches SEC Form 4 insider trading data and returns ``list[dict]``
in memory. Nothing is saved to disk.

Usage::

    import findata

    trades = findata.get_insider_trades("AAPL")
    trades = findata.get_insider_trades("AAPL", count=10)
"""

from __future__ import annotations

import time
from typing import Any

from findata.sec._cik import lookup_cik
from findata.sec.utils.form4.sec_form4_watchlist import fetch_filings
from findata.sec.utils.form4.form4_parser import parse_form4, _TRANSACTION_CODE_DESC


def get_insider_trades(
    ticker: str,
    count: int = 5,
    delay: float = 0.2,
) -> list[dict[str, Any]]:
    """Fetch recent Form 4 insider trades for a ticker.

    Calls SEC EDGAR, parses the XML filings, and returns a flat
    ``list[dict]`` — one dict per (owner × transaction) row.
    Nothing is written to disk.

    Args:
        ticker: Stock symbol (e.g. ``"AAPL"``).
        count:  Number of recent Form 4 filings to fetch.
        delay:  Seconds between SEC requests (rate-limit safe).

    Returns:
        List of trade dicts, sorted by transaction_date descending.

    Raises:
        ValueError: If the ticker cannot be resolved to a CIK.
    """
    cik, _ = lookup_cik(ticker)
    if not cik:
        raise ValueError(f"Unknown ticker: {ticker}")

    filings = fetch_filings(cik, count=count)
    trades: list[dict[str, Any]] = []

    for item in filings:
        link = item.get("link")
        if not link:
            continue
        try:
            parsed = parse_form4(link)
        except Exception as e:
            print(f"  [WARN] Failed to parse {link}: {e}")
            continue

        # Flatten: one row per (owner × transaction)
        issuer = parsed.get("issuer", {})
        rss_meta = item  # title, updated, form_type
        owners = parsed.get("reporting_owners", [])
        transactions = parsed.get("transactions", [])

        for owner in owners:
            rel = owner.get("relationship", {})
            for txn in transactions:
                trade = {
                    "source_url": parsed.get("source_url", ""),
                    "document_type": parsed.get("document_type", ""),
                    "period_of_report": parsed.get("period_of_report", ""),
                    "ticker": parsed.get("ticker", ticker.upper()),
                    "rss_updated": rss_meta.get("updated", ""),

                    "issuer_name": issuer.get("name", ""),
                    "issuer_cik": issuer.get("cik", ""),
                    "issuer_symbol": issuer.get("trading_symbol", ""),

                    "owner_name": owner.get("name", ""),
                    "is_director": rel.get("is_director", ""),
                    "is_officer": rel.get("is_officer", ""),
                    "is_ten_pct_owner": rel.get("is_ten_pct_owner", ""),
                    "is_other": rel.get("is_other", ""),
                    "officer_title": rel.get("officer_title", ""),

                    **txn,  # row_type, security_title, transaction_code, etc.
                }
                trades.append(trade)

        time.sleep(delay)

    # Sort by transaction_date descending
    trades.sort(key=lambda r: r.get("transaction_date", ""), reverse=True)
    return trades
