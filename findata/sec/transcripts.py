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

import os
import re
from typing import Any
from urllib.parse import urlparse


TRANSCRIPT_DOMAINS = [
    "fool.com",
    "rev.com",
    "seekingalpha.com",
    "insidermonkey.com",
    "investing.com",
]

DOMAIN_PRIORITY = {
    "fool.com": 100,
    "rev.com": 80,
    "insidermonkey.com": 60,
    "investing.com": 50,
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

    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY environment variable is not set")

    try:
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.environ.get("TAVILY_API_KEY", api_key)
    except ImportError:
        pass

    from tavily import TavilyClient
    client = TavilyClient(api_key=api_key)

    query = f"{ticker} Q{quarter} {year} earnings call transcript"
    search_resp = client.search(
        query=query,
        include_domains=TRANSCRIPT_DOMAINS,
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
