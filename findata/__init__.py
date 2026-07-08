"""
findata — Financial data library for SEC EDGAR.

Pure library layer: all functions fetch data from public APIs and return
``list[dict]`` in memory. Nothing is saved to disk (except the PDF helpers,
which write when given an ``output_path``).

Usage::

    import findata

    # SEC insider trades (Form 4)
    trades = findata.get_insider_trades("AAPL")

    # SEC 10-K/10-Q filings with parsed sections
    filings = findata.get_filings("AAPL")

    # Resolve filings to their document URLs (no parsing) — never build a
    # SEC URL by hand
    rows = findata.find_filings("AAPL", form_type="10-K", date_from="2021-01-01")

    # SEC XBRL financial facts
    facts = findata.get_financials("AAPL")

    # Earnings call transcript (requires: pip install findata[transcripts])
    transcript = findata.get_transcript("AAPL", year=2024, quarter=4)

    # Download a filing as PDF by ticker (requires: pip install findata[server])
    findata.download_filing_pdf_for("AAPL", form_type="10-K", output_path="aapl.pdf")

    # ...or from a raw URL if you already have one
    findata.download_filing_pdf("https://www.sec.gov/...", output_path="filing.pdf")

For the commercial API server, see ``findata.server``.
"""

from findata.sec.form4 import get_insider_trades
from findata.sec.filings import get_filings, get_filing_text, find_filings
from findata.sec.financials import get_financials
from findata.sec.transcripts import get_transcript
from findata.sec.pdf import download_filing_pdf, download_filing_pdf_for

__all__ = [
    "get_insider_trades",
    "get_filings",
    "get_filing_text",
    "find_filings",
    "get_financials",
    "get_transcript",
    "download_filing_pdf",
    "download_filing_pdf_for",
]
