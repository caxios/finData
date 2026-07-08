"""
SEC filings — library layer.

Fetches 10-K/10-Q filings and generic SEC filing types, returns
``list[dict]`` in memory. Nothing is saved to disk.

Usage::

    import findata

    filings = findata.get_filings("AAPL")
    filings = findata.get_filings("AAPL", form_type="10-Q", count=4)
"""

from __future__ import annotations

import time
from typing import Any

from findata.sec._cik import lookup_cik
from findata.sec.utils.sec_10kq.sec_10kq_rss import fetch_and_resolve
from findata.sec.utils.sec_10kq.sec_10kq_parser import parse_single_filing


def get_filings(
    ticker: str,
    form_type: str = "10-K,10-Q",
    count: int = 4,
    include_archive: bool = False,
    parse_sections: bool = True,
    delay: float = 0.2,
) -> list[dict[str, Any]]:
    """Fetch SEC 10-K/10-Q filings with parsed sections.

    Downloads filing metadata from EDGAR's submissions JSON, then
    optionally downloads and parses the HTML for each filing to extract
    Business, Risk Factors, MD&A, and Financial Notes sections.

    Args:
        ticker:          Stock symbol (e.g. ``"AAPL"``).
        form_type:       Comma-separated form types (default ``"10-K,10-Q"``).
        count:           Number of filings to fetch.
        include_archive: Walk older filing archives for full history.
        parse_sections:  If True, download and parse each filing's HTML.
                         If False, return metadata only (much faster).
        delay:           Seconds between SEC requests.

    Returns:
        List of filing dicts, sorted by filing_date descending.

    Raises:
        ValueError: If the ticker cannot be resolved to a CIK.
    """
    cik, _ = lookup_cik(ticker)
    if not cik:
        raise ValueError(f"Unknown ticker: {ticker}")

    forms = {f.strip() for f in form_type.split(",") if f.strip()}
    filings = fetch_and_resolve(
        cik, count=count, include_archive=include_archive, forms=forms,
    )

    if not parse_sections:
        return filings

    results: list[dict[str, Any]] = []
    for filing in filings:
        if not filing.get("document_url"):
            results.append(filing)
            continue
        try:
            parsed = parse_single_filing(filing)
            results.append(parsed)
        except Exception as e:
            print(f"  [WARN] Failed to parse {filing.get('accession_number')}: {e}")
            results.append(filing)
        time.sleep(delay)

    return results


def find_filings(
    ticker: str,
    form_type: str = "10-K,10-Q",
    date_from: str | None = None,
    date_to: str | None = None,
    count: int = 40,
    include_archive: bool | None = None,
) -> list[dict[str, Any]]:
    """Resolve a ticker + form + date window to filing rows — no parsing.

    This exists so callers never have to build a SEC document URL by hand.
    Each returned row already carries a ready-to-use ``document_url`` (the
    primary-document URL, resolved from EDGAR's submissions JSON), alongside
    ``form_type``, ``filing_date``, and ``accession_number``.

    Selection:
        - No date window          → the most recent ``count`` filings.
        - ``date_from``/``date_to`` → every filing whose *filing date* falls
          within the inclusive window (``count`` is ignored).

    Args:
        ticker:          Stock symbol (e.g. ``"AAPL"``).
        form_type:       Comma-separated form types (default ``"10-K,10-Q"``).
        date_from:       Inclusive lower bound, ``"YYYY-MM-DD"`` (optional).
        date_to:         Inclusive upper bound, ``"YYYY-MM-DD"`` (optional).
        count:           Max rows when no date window is given (default 40).
        include_archive: Walk older archive shards. Defaults to ``True`` when a
                         date window is given (older filings live in archive
                         shards, not the "recent" block), else ``False``.

    Returns:
        List of filing rows sorted by filing_date descending.

    Raises:
        ValueError: If the ticker cannot be resolved to a CIK.
    """
    cik, _ = lookup_cik(ticker)
    if not cik:
        raise ValueError(f"Unknown ticker: {ticker}")

    forms = {f.strip() for f in form_type.split(",") if f.strip()}

    windowed = bool(date_from or date_to)
    if include_archive is None:
        include_archive = windowed
    # When windowing, pull a wide slice so the window isn't truncated by
    # `count` before we filter — the date filter decides the result size.
    fetch_count = 10_000 if windowed else count

    rows = fetch_and_resolve(
        cik, count=fetch_count, include_archive=include_archive, forms=forms,
    )

    if date_from:
        rows = [r for r in rows if r["filing_date"] >= date_from]
    if date_to:
        rows = [r for r in rows if r["filing_date"] <= date_to]

    return rows


def get_filing_text(
    ticker: str,
    form: str,
    document_url: str,
    accession_number: str = "",
    filing_date: str | None = None,
) -> dict[str, Any] | None:
    """Parse a specific filing's text sections (8-K, S-4, SC 13D, 144).

    Downloads the document and parses it using the appropriate parser.
    Returns the parsed result in memory. Nothing is saved to disk.

    Args:
        ticker:           Stock symbol.
        form:             Form type (``"8-K"``, ``"S-4"``, ``"SC 13D"``, ``"144"``).
        document_url:     URL of the primary document.
        accession_number: SEC accession number (optional).
        filing_date:      Filing date (optional).

    Returns:
        Parsed filing dict, or None on failure.
    """
    import requests
    from findata.sec.const import HEADERS

    cik, _ = lookup_cik(ticker)

    # Import form-specific parsers
    from findata.sec.utils.sec_filings import parser_8k, parser_s4, parser_sc13, parser_144

    try:
        resp = requests.get(document_url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        content = resp.text
    except Exception as e:
        print(f"  [WARN] Download failed for {document_url}: {e}")
        return None

    parsers = {
        "8-K": parser_8k.parse_8k,
        "S-4": parser_s4.parse_s4,
        "SC 13D": parser_sc13.parse_sc13,
        "SC 13G": parser_sc13.parse_sc13,
        "144": parser_144.parse_144,
    }

    parse_fn = parsers.get(form)
    if not parse_fn:
        raise ValueError(f"No parser for form type: {form}")

    parsed = parse_fn(content)
    parsed.update({
        "cik": cik,
        "accession_number": accession_number,
        "form_type": form,
        "filing_date": filing_date,
        "document_url": document_url,
    })
    return parsed
