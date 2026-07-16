"""
Earnings call transcripts — library layer.

Fetches earnings call transcripts via Tavily search and returns
a dict in memory. Nothing is saved to disk (no caching — each call
uses Tavily API credits).

Usage::

    import findata

    transcript = findata.get_transcript("AAPL", year=2024, quarter=4)
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


# The transcript source to try first. Only if investing.com yields no usable
# transcript do we search the fallback sources below.
PRIMARY_DOMAIN = "investing.com"

# Searched (as a second Tavily pass) only when the primary domain comes up empty.
FALLBACK_DOMAINS = [
    "fool.com",
    "rev.com",
    "seekingalpha.com",
    "insidermonkey.com",
]

# Full set of domains we may ever search (primary first). Kept for callers/tests
# that reference the overall source list.
TRANSCRIPT_DOMAINS = [PRIMARY_DOMAIN, *FALLBACK_DOMAINS]

# Relative preference used to rank results *within* the fallback pass.
DOMAIN_PRIORITY = {
    "fool.com": 100,
    "rev.com": 80,
    "insidermonkey.com": 60,
    "seekingalpha.com": 40,
}

MIN_TRANSCRIPT_CHARS = 2000


def _domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().lstrip("www.")


def _score_result(result: dict, ticker: str, fiscal_year: int, fiscal_quarter: int) -> int:
    title = (result.get("title") or "").lower()
    url = result.get("url") or ""
    domain = _domain_of(url)

    score = DOMAIN_PRIORITY.get(domain, 0)
    if ticker.lower() in title:
        score += 30
    if str(fiscal_year) in title:
        score += 20
    if re.search(rf"\bq{fiscal_quarter}\b", title):
        score += 20
    if "transcript" in title:
        score += 10
    return score


def _search_and_extract(
    client,
    query: str,
    domains: list[str],
    ticker: str,
    year: int,
    quarter: int,
) -> dict[str, Any] | None:
    """Run one Tavily search restricted to *domains*, then extract the best
    usable transcript from the ranked results.

    Returns a transcript dict, or ``None`` if the search returned nothing or no
    candidate produced a long-enough transcript.
    """
    search_resp = client.search(
        query=query,
        include_domains=domains,
        max_results=8,
        search_depth="advanced",
    )
    results = search_resp.get("results") or []
    if not results:
        return None

    ranked = sorted(
        results,
        key=lambda r: _score_result(r, ticker, year, quarter),
        reverse=True,
    )

    for candidate in ranked:
        url = candidate.get("url")
        if not url:
            continue
        try:
            extract_resp = client.extract(urls=[url], extract_depth="advanced")
        except Exception as e:
            print(f"  [extract failed] {url}: {e}")
            continue

        items = extract_resp.get("results") or []
        if not items:
            continue
        text = (items[0].get("raw_content") or "").strip()
        if len(text) < MIN_TRANSCRIPT_CHARS:
            print(f"  [too short, skipping] {url} ({len(text)} chars)")
            continue

        return {
            "ticker": ticker,
            "fiscal_year": year,
            "fiscal_quarter": quarter,
            "source_url": url,
            "source_domain": _domain_of(url),
            "title": candidate.get("title"),
            "transcript_text": text,
        }

    return None


def get_transcript(
    ticker: str,
    year: int,
    quarter: int,
) -> dict[str, Any] | None:
    """Fetch an earnings call transcript via Tavily.

    Searches for the transcript across multiple sources, extracts the
    best match, and returns it in memory. Nothing is cached to disk —
    each call uses Tavily API credits.

    Args:
        ticker:  Stock symbol (e.g. ``"AAPL"``).
        year:    Fiscal year (e.g. ``2024``).
        quarter: Fiscal quarter (``1``–``4``).

    Returns:
        Dict with keys: ticker, fiscal_year, fiscal_quarter, source_url,
        source_domain, title, transcript_text.
        Returns ``None`` if no suitable transcript was found.

    Raises:
        ValueError:    If quarter is not 1-4.
        RuntimeError:  If TAVILY_API_KEY is not set.
    """
    if not (1 <= quarter <= 4):
        raise ValueError("quarter must be 1-4")

    ticker = ticker.upper()

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY environment variable is not set")

    from tavily import TavilyClient
    client = TavilyClient(api_key=api_key)

    query = f"{ticker} Q{quarter} {year} earnings call transcript"

    # Phase 1 — try investing.com first.
    transcript = _search_and_extract(
        client, query, [PRIMARY_DOMAIN], ticker, year, quarter
    )
    if transcript is not None:
        return transcript

    # Phase 2 — investing.com had nothing usable; fall back to the other sources.
    print(f"  [{PRIMARY_DOMAIN} miss] falling back to "
          f"{', '.join(FALLBACK_DOMAINS)}")
    return _search_and_extract(
        client, query, FALLBACK_DOMAINS, ticker, year, quarter
    )


def _expand_quarters(
    year_from: int,
    quarter_from: int,
    year_to: int,
    quarter_to: int,
) -> list[tuple[int, int]]:
    """Enumerate every (year, quarter) from the start to the end quarter.

    Quarters are treated as a single running index (``year*4 + (quarter-1)``)
    so the range spans year boundaries. The bounds are inclusive, and swapped
    if given in reverse order.
    """
    start = year_from * 4 + (quarter_from - 1)
    end = year_to * 4 + (quarter_to - 1)
    if end < start:
        start, end = end, start
    return [(idx // 4, idx % 4 + 1) for idx in range(start, end + 1)]


def download_transcripts_for(
    ticker: str,
    year_from: int,
    quarter_from: int,
    year_to: int | None = None,
    quarter_to: int | None = None,
    output_path: str | Path | None = None,
) -> bytes:
    """Download earnings call transcript(s) as text by ticker + quarter range.

    The transcript analog of :func:`findata.download_filing_pdf_for`: instead of
    one filing you give a range of fiscal quarters, and each is resolved via
    :func:`get_transcript` (Tavily search + extract) and written out as plain
    text. Stateless — nothing is cached; each quarter spends Tavily credits.

    Selection:
        - Single quarter (no ``*_to``) → the transcript text as UTF-8 bytes.
        - Multiple quarters            → a ZIP archive (one ``.txt`` per call).

    Quarters with no findable transcript are skipped with a warning; the result
    contains only the ones that were found. Raises if none were found at all.

    Args:
        ticker:        Stock symbol (e.g. ``"AAPL"``).
        year_from:     Fiscal year of the first quarter (e.g. ``2020``).
        quarter_from:  Fiscal quarter of the first quarter (``1``-``4``).
        year_to:       Fiscal year of the last quarter. Defaults to ``year_from``.
        quarter_to:    Fiscal quarter of the last quarter. Defaults to
                       ``quarter_from`` (i.e. a single quarter).
        output_path:   If given, also write the result (txt or zip) to this path.

    Returns:
        UTF-8 text bytes (single quarter) or ZIP bytes (multiple quarters).

    Raises:
        ValueError:   If a quarter is outside 1-4, or no transcript was found.
        RuntimeError: If TAVILY_API_KEY is not set.
    """
    ticker = ticker.upper()
    if year_to is None:
        year_to = year_from
    if quarter_to is None:
        quarter_to = quarter_from

    quarters = _expand_quarters(year_from, quarter_from, year_to, quarter_to)

    found: list[tuple[str, str]] = []  # (filename, transcript_text)
    for year, quarter in quarters:
        transcript = get_transcript(ticker, year=year, quarter=quarter)
        if not transcript:
            print(f"  [not found] {ticker} Q{quarter} {year} — skipping")
            continue
        name = f"{ticker}_{year}_Q{quarter}.txt"
        text = transcript["transcript_text"]
        found.append((name, text))
        print(f"  [ok] {name} ({len(text):,} chars) <- {transcript['source_domain']}")

    if not found:
        raise ValueError(
            f"No transcripts found for {ticker} in the requested quarter range "
            f"({year_from} Q{quarter_from} .. {year_to} Q{quarter_to})."
        )

    if len(found) == 1:
        result_bytes = found[0][1].encode("utf-8")
    else:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, text in found:
                zf.writestr(name, text)
        result_bytes = buf.getvalue()

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(result_bytes)

    return result_bytes
