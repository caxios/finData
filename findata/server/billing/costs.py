"""
Endpoint credit costs — the single source of truth for metering weights.

Each API call consumes a number of **credits** proportional to its real cost.
Cache reads are cheap (1 credit); upstream-calling endpoints (Tavily, LLM)
are weighted much higher.

Tune these numbers against measured upstream costs. Billing (03) will
convert credits to dollars.
"""

from __future__ import annotations

# ── Credit costs per endpoint ───────────────────────────────────────
# Key: route path pattern (matches request.url.path).
# Value: credit cost for that endpoint.
#
# For path-templated routes (e.g. /api/trades/{id}), we match by prefix
# or exact path.  The lookup function below handles this.

ENDPOINT_COSTS: dict[str, int] = {
    # ── Cache reads (cheap: DB read only) ───────────────────────────
    "/api/trades":                          1,
    "/api/trades/":                         1,   # with trailing slash
    "/api/summary":                         1,
    "/api/watchlist":                       1,
    "/api/form4/rankings":                  1,
    "/api/documents/":                      1,   # /api/documents/{ticker}/list, /api/documents/{ticker}/{acc}
    "/api/financials/":                     1,   # /api/financials/{ticker}/list, /api/financials/{ticker}/detail
    "/api/transcripts/":                    1,   # /api/transcripts/{ticker}/list (cached list)
    "/api/sec-filings/":                    2,   # may hit EDGAR submissions.json

    # ── Lazy-fetch (cache miss triggers upstream EDGAR call) ────────
    "/api/company-data/":                   3,   # orchestrator, may trigger multiple fetches
    "/api/filing-text/":                    3,   # downloads + parses filing document
    "/api/refresh":                         5,   # bulk scrape trigger
    "/api/download-pdf":                    5,   # Playwright PDF render

    # ── Paid upstream (real per-call cost) ──────────────────────────
    "/api/transcript":                      10,  # Tavily search call
    "/api/filings/chat":                    20,  # Google GenAI multi-agent
    "/api/filings/chat/reset":              1,   # just memory clear
}

# Default for any unmatched endpoint
DEFAULT_COST: int = 1

# Extra credits added when a request triggers an on-demand upstream fetch
# (cache miss / historical backfill on /api/trades — see plan 05 §3.3).
# Endpoints signal this per-request via ``request.state.extra_credits``; the
# metering middleware adds it on top of the base endpoint cost. This is how a
# cache-miss becomes a "higher-credit event" without a separate path.
LAZY_FETCH_CREDITS: int = 3


def get_endpoint_credits(path: str) -> int:
    """Resolve the credit cost for a request path.

    Checks exact match first, then prefix match for path-templated routes.
    """
    # Exact match
    if path in ENDPOINT_COSTS:
        return ENDPOINT_COSTS[path]

    # Prefix match (for routes like /api/trades/123, /api/documents/AAPL/list)
    for pattern, cost in ENDPOINT_COSTS.items():
        if pattern.endswith("/") and path.startswith(pattern):
            return cost

    return DEFAULT_COST
