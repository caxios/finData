"""
finData - Unified financial data fetcher for Korean and US markets.

Usage:
    import findata

    # US SEC data
    data = findata.get_sec_financials("AAPL")

    # Earnings call transcript (requires: pip install findata[transcripts])
    transcript = findata.fetch_transcript("AAPL", fiscal_year=2024, fiscal_quarter=4)
"""

from findata.sec.company_data import get_company_data as get_sec_financials


def fetch_transcript(
    ticker: str,
    fiscal_year: int,
    fiscal_quarter: int,
    force_refresh: bool = False,
    **kwargs,
) -> dict | None:
    """Fetch an earnings call transcript. Requires tavily-python.

    Install with: pip install findata[transcripts]
    """
    try:
        from findata.sec.utils.earnings_call.tavily_transcripts import (
            fetch_transcript as _fetch,
        )
    except ImportError as e:
        raise ImportError(
            "fetch_transcript requires the 'tavily-python' package. "
            "Install it with: pip install findata[transcripts]"
        ) from e

    return _fetch(
        ticker=ticker,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        force_refresh=force_refresh,
        **kwargs,
    )


__all__ = [
    "get_sec_financials",
    "fetch_transcript",
]
