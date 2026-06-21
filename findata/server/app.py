"""
FastAPI server for the findata commercial API.

Serves data from SQLite databases with caching and lazy-loading.
All data endpoints require API key authentication and are metered.

Run:
    python -m findata.server.app
    # or
    uvicorn findata.server.app:app --reload --port 8000
"""
import os
import sys
import asyncio
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from findata.server.api import api_form4, api_earnigscall, api_10kq, api_cio_chat
from findata.server.auth import require_api_key, require_gateway
from findata.server.quota import check_quota
from findata.server.billing.guardrail import circuit_breaker
from findata.server.db.config import ensure_data_dirs
from findata.server.db.accounts_db import ensure_accounts_schema
from findata.server.db.usage_db import ensure_usage_schema, get_usage_summary
from findata.server.billing.upstream_cost import ensure_upstream_schema
from findata.server.middleware.metering import MeteringMiddleware
from findata.server.middleware.ratelimit import RateLimitMiddleware
from findata.server.billing.plans import get_plan


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
# Windows event loop policy
if sys.platform in ("win32", "win64"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(
    title="findata API Server",
    description="Commercial API for SEC EDGAR and OpenDART financial data.",
    version="0.2.0",
)


@app.on_event("startup")
def _startup() -> None:
    ensure_data_dirs()
    ensure_accounts_schema()
    ensure_usage_schema()
    ensure_upstream_schema()
    _maybe_start_form4_poller()
    _maybe_start_scheduled_ingestion()


# ── Form 4 background poller (single-instance MVP, opt-in) ───────────
# Gated behind ENABLE_FORM4_POLLER so only ONE process runs it (running it
# in every API instance would cause duplicate polling + write contention).
# For multi-instance deployments, run the worker separately instead — see
# 04_form4_realtime_polling.md §3.3 and 08_deployment_and_infra.md.
_poller_stop = None


def _maybe_start_form4_poller() -> None:
    global _poller_stop
    if os.getenv("ENABLE_FORM4_POLLER", "0") != "1":
        return
    from findata.server.ingestion.form4_poller import (
        start_background_poller,
        DEFAULT_POLL_INTERVAL,
    )
    interval = int(os.getenv("FORM4_POLL_INTERVAL", str(DEFAULT_POLL_INTERVAL)))
    _poller_stop = start_background_poller(poll_interval=interval)


# ── Scheduled ingestion (financials/filings; single-instance MVP, opt-in) ──
# Gated behind ENABLE_SCHEDULED_INGESTION so only ONE process runs it. For
# multi-instance deployments, run the worker separately (08_deployment_and_infra).
_scheduler_stop = None


def _maybe_start_scheduled_ingestion() -> None:
    global _scheduler_stop
    if os.getenv("ENABLE_SCHEDULED_INGESTION", "0") != "1":
        return
    from findata.server.ingestion.scheduled import start_background_scheduler
    _scheduler_stop = start_background_scheduler()


@app.on_event("shutdown")
def _shutdown() -> None:
    if _poller_stop is not None:
        _poller_stop.set()
    if _scheduler_stop is not None:
        _scheduler_stop.set()


# ── Middleware (order matters: outermost runs first) ─────────────────
# 1. CORS (outermost)
_cors_origins_raw = os.getenv("FINDATA_CORS_ORIGINS", "*")
_cors_origins = (
    ["*"]
    if _cors_origins_raw.strip() == "*"
    else [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Metering (records usage after response — must be added after CORS
#    but Starlette middleware stack is LIFO, so add metering first so it
#    runs closest to the actual response)
app.add_middleware(MeteringMiddleware)

# 3. Rate limiting (runs before the handler, after auth)
app.add_middleware(RateLimitMiddleware)


# ── Public endpoints (no auth) ──────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check():
    """Health check endpoint — no authentication required."""
    return {"status": "ok"}


@app.get("/api/health/poller", tags=["System"])
def poller_health():
    """Form 4 poller status (last run, counts, failures) — no auth required."""
    from findata.server.ingestion.form4_poller import get_poller_status
    status = get_poller_status()
    enabled = os.getenv("ENABLE_FORM4_POLLER", "0") == "1"
    return {"enabled": enabled, **status}


# ── Data routers (auth + gateway + quota + cost guardrail) ──────────
# Applied uniformly at router registration so no endpoint can be
# accidentally left unauthenticated, unmetered, or unguarded. Order:
#   1. require_api_key  → authenticate, set request.state.user
#   2. require_gateway  → enforce gateway-only access (owner-exempt, Track A)
#   3. check_quota      → monthly credit quota (owner-exempt)
#   4. circuit_breaker  → trip 503 on paid endpoints when over budget (09 §3.5)
_auth_deps = [
    Depends(require_api_key),
    Depends(require_gateway),
    Depends(check_quota),
    Depends(circuit_breaker),
]

app.include_router(api_form4.router, dependencies=_auth_deps)
app.include_router(api_earnigscall.router, dependencies=_auth_deps)
app.include_router(api_10kq.router, dependencies=_auth_deps)
app.include_router(api_cio_chat.router, dependencies=_auth_deps)


# ── Usage endpoint (authenticated, shows caller's own usage) ────────

@app.get("/api/usage", tags=["System"], dependencies=[Depends(require_api_key)])
def get_usage(request: Request):
    """Return the caller's credit usage for the current billing period."""
    user = request.state.user
    plan = get_plan(user.get("plan", "free"))
    summary = get_usage_summary(user["user_id"])
    summary["plan"] = user.get("plan", "free")
    summary["credits_limit"] = plan.monthly_credits  # None for unlimited
    return summary


# ── Admin: Track 0 upstream cost summary (owner only) ───────────────

@app.get("/api/admin/upstream-costs", tags=["System"], dependencies=[Depends(require_api_key)])
def get_upstream_costs(request: Request):
    """Owner-only: per-endpoint upstream cost + avg $/call for the period.

    Use ``avg_usd_per_call`` to calibrate the credit weights in
    ``billing/costs.py`` so each paid endpoint's price covers its real cost
    (plan 03 Track 0).
    """
    from fastapi import HTTPException
    from findata.server.billing.upstream_cost import get_upstream_cost_summary

    user = request.state.user
    if user.get("plan") != "owner":
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "FORBIDDEN", "message": "Owner access required."}},
        )
    return get_upstream_cost_summary()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("findata.server.app:app", host="0.0.0.0", port=8000, reload=True)
