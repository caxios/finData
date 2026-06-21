"""
Metering middleware — records per-request credit usage after the response.

Runs as Starlette middleware so it captures the final HTTP status code.
Skips recording for:
- Owner plan users (credits = 0, still logged for visibility)
- Unauthenticated requests (they'll be 401'd by the auth dependency)
- System endpoints (/health, /docs, /openapi.json)
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from findata.server.billing.costs import get_endpoint_credits
from findata.server.db import usage_db as _usage_db


# Paths that should never be metered
_SKIP_PATHS = frozenset({"/health", "/docs", "/redoc", "/openapi.json"})


class MeteringMiddleware(BaseHTTPMiddleware):
    """Record credit usage for every authenticated API call."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        # Skip system/public endpoints
        path = request.url.path
        if path in _SKIP_PATHS:
            return response

        # Only meter authenticated requests
        user = getattr(request.state, "user", None)
        if user is None:
            return response

        # Resolve credit cost: base (by path) + any per-request extra a handler
        # set on cache miss / backfill (e.g. /api/trades lazy fetch, plan 05).
        credits = get_endpoint_credits(path)
        extra = getattr(request.state, "extra_credits", 0) or 0
        credits += int(extra)

        # Owner: record at 0 credits for visibility, but don't charge
        if user.get("plan") == "owner":
            credits = 0

        # Record usage (fire-and-forget; don't fail the response)
        try:
            _usage_db.record_usage(
                user_id=user["user_id"],
                endpoint=path,
                credits=credits,
                status_code=response.status_code,
            )
        except Exception:
            pass  # Never fail a request over metering

        return response
