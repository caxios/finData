"""
Lightweight CIK resolver for the library layer.

Uses sec_cik_mapper (offline JSON mapping) — no SQLite dependency.
This is the library-layer replacement for agents.data_loader._lookup_cik.
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _get_mapper():
    """Lazily load StockMapper once and cache it."""
    from sec_cik_mapper import StockMapper
    return StockMapper()


def lookup_cik(ticker: str) -> tuple[str | None, str | None]:
    """Resolve ticker → (CIK zero-padded, entity_name).

    Returns (None, None) if the ticker is unknown.
    Uses sec_cik_mapper's offline JSON — no network call, no database.
    """
    mapper = _get_mapper()
    cik = mapper.ticker_to_cik.get(ticker.upper())
    if cik:
        return cik, ticker.upper()
    return None, None
