"""
FastAPI authentication dependencies for the findata commercial API.

Provides ``require_api_key`` and ``optional_api_key`` dependencies that
extract and validate client API keys from request headers.

Usage::

    from findata.server.auth import require_api_key

    router = APIRouter(dependencies=[Depends(require_api_key)])
"""

import os
import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

from findata.server.db import accounts_db as _accounts_db


# Accept key via either header style
_header_bearer = APIKeyHeader(
    name="Authorization",
    auto_error=False,
    description="Bearer <api_key>",
)
_header_x_api_key = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Raw API key",
)
# Shared secret injected by the billing gateway (Track A). The Origin server
# trusts only requests carrying this header — except the owner, who reaches
# Origin directly over a private path (self-exemption A).
_header_gateway = APIKeyHeader(
    name="X-Gateway-Secret",
    auto_error=False,
    description="Shared secret proving the request came through the billing gateway",
)


def _extract_key(
    auth_header: str | None,
    x_api_key: str | None,
) -> str | None:
    """Extract the raw API key from whichever header was provided."""
    if x_api_key:
        return x_api_key
    if auth_header:
        # Support "Bearer <key>" format
        parts = auth_header.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
        # Also accept raw key in Authorization header
        return auth_header
    return None


async def require_api_key(
    request: Request,
    auth_header: str | None = Depends(_header_bearer),
    x_api_key: str | None = Depends(_header_x_api_key),
) -> dict:
    """FastAPI dependency that enforces API key authentication.

    On success, injects the user dict into ``request.state.user`` and
    returns it.  On failure, raises 401.

    The user dict contains:
        key_id, user_id, key_prefix, key_label, active,
        last_used_at, email, plan
    """
    raw_key = _extract_key(auth_header, x_api_key)

    if not raw_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "MISSING_API_KEY",
                    "message": (
                        "API key required. Provide via "
                        "'Authorization: Bearer <key>' or 'X-API-Key: <key>' header."
                    ),
                }
            },
        )

    user = _accounts_db.get_user_by_key(raw_key)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "INVALID_API_KEY",
                    "message": "The provided API key is invalid or has been deactivated.",
                }
            },
        )

    # Inject into request state for downstream use (metering, logging, etc.)
    request.state.user = user

    # Update last_used_at (fire-and-forget; non-critical)
    try:
        _accounts_db.update_last_used(user["key_id"])
    except Exception:
        pass  # Don't fail the request over a timestamp update

    return user


async def optional_api_key(
    request: Request,
    auth_header: str | None = Depends(_header_bearer),
    x_api_key: str | None = Depends(_header_x_api_key),
) -> dict | None:
    """Like ``require_api_key`` but allows unauthenticated access.

    If a key is provided and valid, injects the user into
    ``request.state.user``. If no key is provided, sets
    ``request.state.user = None`` and returns None.
    Raises 401 only if a key IS provided but is invalid.
    """
    raw_key = _extract_key(auth_header, x_api_key)

    if not raw_key:
        request.state.user = None
        return None

    user = _accounts_db.get_user_by_key(raw_key)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "INVALID_API_KEY",
                    "message": "The provided API key is invalid or has been deactivated.",
                }
            },
        )

    request.state.user = user

    try:
        _accounts_db.update_last_used(user["key_id"])
    except Exception:
        pass

    return user


def _gateway_secret() -> str | None:
    """Read the gateway shared secret from the environment (None = disabled)."""
    secret = os.getenv("FINDATA_GATEWAY_SECRET")
    return secret or None


async def require_gateway(
    request: Request,
    gateway_secret: str | None = Depends(_header_gateway),
) -> None:
    """Enforce that requests arrive through the billing gateway (Track A).

    Must run *after* ``require_api_key`` so ``request.state.user`` is set.

    Behavior:
    - If ``FINDATA_GATEWAY_SECRET`` is not configured → no-op (local dev).
    - Owner-plan users bypass the check — they reach Origin over a private
      path (self-exemption A), not through the gateway.
    - Everyone else must present a matching ``X-Gateway-Secret`` header,
      otherwise 403. This stops users from hitting Origin directly to
      bypass billing/metering at the gateway edge.
    """
    secret = _gateway_secret()
    if secret is None:
        return  # gateway enforcement disabled

    user = getattr(request.state, "user", None)
    if user is not None and user.get("plan") == "owner":
        return  # owner private path bypasses the gateway

    if not gateway_secret or not secrets.compare_digest(gateway_secret, secret):
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "GATEWAY_REQUIRED",
                    "message": (
                        "This API must be accessed through the official gateway. "
                        "Direct access to the origin server is not permitted."
                    ),
                }
            },
        )
