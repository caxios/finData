"""
Rate limiter — per-key token bucket with owner exemption.

Uses an in-memory token bucket per user_id.  Suitable for a single
server instance; switch to Redis-backed buckets for multi-instance
deployment (see 08_deployment_and_infra.md).

Returns 429 with ``Retry-After`` header when the bucket is empty.
"""

import time
import threading
from dataclasses import dataclass, field

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from findata.server.billing.plans import get_plan


@dataclass
class TokenBucket:
    """Simple token bucket rate limiter."""
    rate: float          # tokens per second
    burst: int           # max tokens
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = float(self.burst)
        self.last_refill = time.monotonic()

    def consume(self, cost: int = 1) -> float | None:
        """Try to consume ``cost`` tokens.

        Returns None on success, or the seconds to wait on failure.
        """
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_refill = now

        if self.tokens >= cost:
            self.tokens -= cost
            return None  # success

        # How long until enough tokens are available
        deficit = cost - self.tokens
        return deficit / self.rate


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-user token bucket rate limiter.

    Owner-plan users are exempt from rate limiting.
    """

    def __init__(self, app, **kwargs) -> None:
        super().__init__(app, **kwargs)
        self._buckets: dict[int, TokenBucket] = {}
        self._lock = threading.Lock()

    def _get_bucket(self, user_id: int, plan_name: str) -> TokenBucket:
        """Get or create a token bucket for a user."""
        with self._lock:
            if user_id not in self._buckets:
                plan = get_plan(plan_name)
                self._buckets[user_id] = TokenBucket(
                    rate=plan.rate_limit_per_second,
                    burst=plan.rate_limit_burst,
                )
            return self._buckets[user_id]

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Only rate-limit authenticated requests
        user = getattr(request.state, "user", None)
        if user is None:
            return await call_next(request)

        # Owner exempt
        if user.get("plan") == "owner":
            return await call_next(request)

        bucket = self._get_bucket(user["user_id"], user.get("plan", "free"))
        retry_after = bucket.consume(1)

        if retry_after is not None:
            retry_after_int = max(1, int(retry_after) + 1)
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": (
                            f"Rate limit exceeded. "
                            f"Retry after {retry_after_int} second(s)."
                        ),
                        "retry_after": retry_after_int,
                    }
                },
                headers={"Retry-After": str(retry_after_int)},
            )

        return await call_next(request)
