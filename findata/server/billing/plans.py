"""
Plan definitions — quota limits and rate limits per billing plan.

Each plan defines:
- ``monthly_credits``: max credits per calendar month (None = unlimited).
- ``rate_limit_per_second``: sustained request rate.
- ``rate_limit_burst``: max burst size for the token bucket.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PlanConfig:
    """Configuration for a billing plan."""
    monthly_credits: Optional[int]   # None = unlimited
    rate_limit_per_second: float     # tokens added per second
    rate_limit_burst: int            # max tokens in bucket
    price_usd_per_month: float = 0.0  # flat monthly subscription price (USD)


# ── Plan registry ───────────────────────────────────────────────────
# Add new plans here.  The key must match the ``plan`` column in the
# ``users`` table.

PLANS: dict[str, PlanConfig] = {
    "owner": PlanConfig(
        monthly_credits=None,         # unlimited
        rate_limit_per_second=100.0,   # effectively unlimited
        rate_limit_burst=200,
        price_usd_per_month=0.0,       # the developer (me) — always free
    ),
    "free": PlanConfig(
        monthly_credits=1_000,         # ~1000 cache reads / month
        rate_limit_per_second=2.0,
        rate_limit_burst=10,
        price_usd_per_month=0.0,
    ),
    "pro": PlanConfig(
        monthly_credits=50_000,        # ~50k cache reads or ~2.5k transcript calls
        rate_limit_per_second=10.0,
        rate_limit_burst=30,
        price_usd_per_month=49.0,
    ),
}

# Fallback for unknown plans (treat as most restrictive)
DEFAULT_PLAN = PLANS["free"]


def get_plan(plan_name: str) -> PlanConfig:
    """Look up plan config by name, falling back to the default plan."""
    return PLANS.get(plan_name, DEFAULT_PLAN)


# ── Pricing model (plan 03 §3.2) ────────────────────────────────────
# Credits → dollars.  A credit is calibrated to ~one cache read, whose
# variable cost is ~0; the price per credit therefore mostly reflects
# amortized fixed server cost + margin.  Paid-upstream endpoints consume
# many credits (see ``billing/costs.py``), so their price scales with
# their real cost.  Tune ``MARGIN`` and ``USD_PER_CREDIT`` against the
# measured upstream cost (Track 0 — see ``billing/upstream_cost.py``).

MARGIN: float = 0.30          # 30% markup over cost
USD_PER_CREDIT: float = 0.0010  # $0.001 / credit  (1,000 credits ≈ $1)


def credits_to_usd(credits: int) -> float:
    """Convert a number of credits to a USD amount (overage / metered billing)."""
    return round(credits * USD_PER_CREDIT, 6)


def price_with_margin(cost_usd: float) -> float:
    """Apply the standard margin to a measured upstream cost.

    Use this with the per-call cost measured in Track 0 to derive the
    minimum price (and thus the credit weight) for a paid-upstream endpoint.
    """
    return round(cost_usd * (1.0 + MARGIN), 6)


def get_plan_price(plan_name: str) -> float:
    """Return the flat monthly subscription price (USD) for a plan."""
    return get_plan(plan_name).price_usd_per_month
