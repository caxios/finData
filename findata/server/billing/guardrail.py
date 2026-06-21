"""
Cost & abuse guardrail — circuit breaker for paid-upstream endpoints.

Implements plan 09 §3.5: a monthly upstream-spend budget that, when
crossed, trips a circuit breaker on the paid-upstream endpoints
(``/api/transcript``, ``/api/filings/chat``) and returns 503 instead of
continuing to "bleed money" on Tavily / Google GenAI calls.

The budget is read from the ``FINDATA_UPSTREAM_MONTHLY_BUDGET_USD``
environment variable.  If it is unset, the breaker is disabled (useful for
local dev).  Owner-plan users bypass the breaker (it's the developer's own
spend and own decision to keep going).

Cache-serving endpoints are never affected — only the two paths that incur
real per-call upstream cost.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request

from findata.server.billing import upstream_cost as _uc


# Only these endpoints incur real upstream cost (see billing/costs.py weights).
PAID_UPSTREAM_PATHS = frozenset({"/api/transcript", "/api/filings/chat"})


def _budget_usd() -> float | None:
    """Read the monthly upstream budget from the environment (None = disabled)."""
    raw = os.getenv("FINDATA_UPSTREAM_MONTHLY_BUDGET_USD")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


async def circuit_breaker(request: Request) -> None:
    """FastAPI dependency: trip 503 on paid endpoints when over budget.

    No-op for:
    - non-paid-upstream paths (cache reads, etc.)
    - owner-plan users (developer's own spend)
    - when no budget is configured
    """
    path = request.url.path
    if path not in PAID_UPSTREAM_PATHS:
        return

    # Owner (the developer) is exempt — their own spend, their own call.
    user = getattr(request.state, "user", None)
    if user is not None and user.get("plan") == "owner":
        return

    budget = _budget_usd()
    if budget is None:
        return

    spent = _uc.get_month_upstream_usd()
    if spent >= budget:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "UPSTREAM_BUDGET_EXCEEDED",
                    "message": (
                        "This endpoint is temporarily unavailable: the monthly "
                        "upstream cost budget has been reached. Cached endpoints "
                        "remain available."
                    ),
                    "spent_usd": round(spent, 4),
                    "budget_usd": round(budget, 4),
                }
            },
        )
