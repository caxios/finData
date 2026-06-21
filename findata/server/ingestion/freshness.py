"""
Cache freshness / TTL policy — single source of truth (plan 06 §3.3).

TTLs were previously hard-coded in ``company_data.py``; duplicating them in the
schedulers would let the values drift. Both the read path (``company_data``) and
the schedulers import from here.

Cadence guidance (see plan 06 §3.2): financials are *immutable once filed* but
new ones drop on irregular dates, so the schedulers should *check* daily even
though a given filing's TTL is long — a daily check is cheap (dedup), and
"refresh once a quarter" would miss the day a new report lands.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# Per-data-type freshness window, in days.
TTL_DAYS: dict[str, int] = {
    "10kq": 90,        # 10-K / 10-Q: quarterly cadence
    "form4": 7,        # insider trades: frequent
    "dart": 90,        # OpenDART periodic reports: quarterly
    "transcript": 365,  # earnings transcripts: effectively immutable once found
}

DEFAULT_TTL_DAYS = 90


def get_ttl_days(kind: str) -> int:
    """Return the TTL (days) for a data type, or the default if unknown."""
    return TTL_DAYS.get(kind, DEFAULT_TTL_DAYS)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        return None


def is_within_ttl(latest_date: str | None, kind: str) -> bool:
    """True if ``latest_date`` (YYYY-MM-DD...) is within the TTL window for kind."""
    parsed = _parse_date(latest_date)
    if parsed is None:
        return False
    return parsed >= datetime.utcnow() - timedelta(days=get_ttl_days(kind))
