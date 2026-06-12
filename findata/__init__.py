"""
findata — Financial data library for SEC and OpenDART.

Pure library layer: all functions fetch data from public APIs and return
``list[dict]`` in memory. Nothing is saved to disk.

Usage::

    import findata

    # SEC insider trades (Form 4)
    trades = findata.get_insider_trades("AAPL")

    # SEC 10-K/10-Q filings with parsed sections
    filings = findata.get_filings("AAPL")

    # SEC XBRL financial facts
    facts = findata.get_financials("AAPL")

    # Earnings call transcript (requires: pip install findata[transcripts])
    transcript = findata.get_transcript("AAPL", year=2024, quarter=4)

For the commercial API server, see ``findata.server``.
"""

from findata.sec.form4 import get_insider_trades
from findata.sec.filings import get_filings, get_filing_text
from findata.sec.financials import get_financials
from findata.sec.transcripts import get_transcript

__all__ = [
    "get_insider_trades",
    "get_filings",
    "get_filing_text",
    "get_financials",
    "get_transcript",
]
