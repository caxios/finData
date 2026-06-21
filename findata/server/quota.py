"""
Quota enforcement dependency — checks monthly credit usage before processing.

Raises 429 if the user has exceeded their plan's monthly credit quota.
Owner-plan users are exempt (unlimited credits).
"""

from datetime import datetime, timezone

from fastapi import HTTPException, Request

from findata.server.billing.costs import get_endpoint_credits
from findata.server.billing.plans import get_plan
from findata.server.db import usage_db as _usage_db


async def check_quota(request: Request) -> None:
    """FastAPI dependency that enforces monthly quota limits.

    Must run after ``require_api_key`` so ``request.state.user`` is set.
    Raises 429 with quota information if the user would exceed their limit.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        return  # unauthenticated → will be caught by auth dependency

    plan_name = user.get("plan", "free")
    plan = get_plan(plan_name)

    # Owner: unlimited
    if plan.monthly_credits is None:
        return

    # Check current usage + cost of this request
    credits_used = _usage_db.get_month_credits(user["user_id"])
    request_cost = get_endpoint_credits(request.url.path)

    if credits_used + request_cost > plan.monthly_credits:
        # Calculate reset date (first of next month)
        now = datetime.now(timezone.utc)
        if now.month == 12:
            reset = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            reset = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "code": "QUOTA_EXCEEDED",
                    "message": (
                        f"Monthly credit quota exceeded. "
                        f"Used {credits_used}/{plan.monthly_credits} credits. "
                        f"Resets on {reset.strftime('%Y-%m-%d')}."
                    ),
                    "credits_used": credits_used,
                    "credits_limit": plan.monthly_credits,
                    "reset": reset.isoformat(),
                }
            },
        )
