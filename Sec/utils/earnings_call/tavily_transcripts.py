"""
On-demand earnings call transcript pipeline.

Flow: cache check → Tavily search (domain-restricted) → rank candidates →
Tavily extract → length sanity check → save to earnings_transcripts.db.
"""
import os
import re
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
except ImportError:
    pass

from tavily import TavilyClient

from earnings_call.earnings_transcripts_db import find_cached, save_transcript


TRANSCRIPT_DOMAINS = [
    "fool.com",
    "rev.com",
    "seekingalpha.com",
    "insidermonkey.com",
    "investing.com",
]

# Higher score = preferred source. Anything not listed gets 0.
DOMAIN_PRIORITY = {
    "fool.com":          100,
    "rev.com":            80,
    "insidermonkey.com":  60,
    "investing.com":      50,
    "seekingalpha.com":   40,  # often paywalled, ranked low
}

# Below this length, the extracted page is almost certainly a paywall stub
# or a search-results page rather than a real transcript.
MIN_TRANSCRIPT_CHARS = 2000


def _domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().lstrip("www.")


def _score_result(result: dict, ticker: str, fiscal_year: int, fiscal_quarter: int) -> int:
    """Rank a Tavily search hit by domain quality + title relevance."""
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


def fetch_transcript(
    ticker: str,
    fiscal_year: int,
    fiscal_quarter: int,
    db_path: str = os.path.join(os.path.dirname(__file__), "db", "earnings_transcripts.db"),
    force_refresh: bool = False,
) -> dict | None:
    """
    Fetch the earnings call transcript for ticker/year/quarter.

    Returns the saved DB row (dict). Returns None if nothing usable was found.
    Cached results are returned immediately unless force_refresh=True.
    """
    if not (1 <= fiscal_quarter <= 4):
        raise ValueError("fiscal_quarter must be 1-4")

    ticker = ticker.upper()

    if not force_refresh:
        cached = find_cached(db_path, ticker, fiscal_year, fiscal_quarter)
        if cached and len(cached.get("transcript_text") or "") >= MIN_TRANSCRIPT_CHARS:
            return cached

    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY environment variable is not set")

    client = TavilyClient(api_key=api_key)

    query = f"{ticker} Q{fiscal_quarter} {fiscal_year} earnings call transcript"
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
        key=lambda r: _score_result(r, ticker, fiscal_year, fiscal_quarter),
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

        return save_transcript(
            db_path,
            ticker=ticker,
            fiscal_year=fiscal_year,
            fiscal_quarter=fiscal_quarter,
            source_url=url,
            transcript_text=text,
            title=candidate.get("title"),
        )

    return None
