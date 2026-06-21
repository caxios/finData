# 02 — Usage Metering & Rate Limiting

> **Phase 1 / Order 2**
> **Prerequisite**: [01_auth_and_api_keys.md](01_auth_and_api_keys.md) (needs `request.state.user`)
> **Related**: [03_billing_and_pricing.md](03_billing_and_pricing.md)

---

## 1. Goal

- Record **how much each user calls** (the basis for billing).
- Enforce **quotas** (monthly/daily caps) and **rate limits** (requests per second/minute).
- Exempt the **owner** (me) from both.

---

## 2. Current State (Code-Grounded)

- No metering or rate limiting anywhere. No per-request accounting.
- Endpoints have **very different real costs** (see [00 §3](00_overview.md)):
  - Cache-serving: `/api/trades`, `/api/summary`, `/api/documents/*`, `/api/financials/*` — cheap.
  - Paid-upstream: `/api/transcript` ([api_earnigscall.py](../../findata/server/api/api_earnigscall.py), Tavily), `/api/filings/chat` ([api_cio_chat.py](../../findata/server/api/api_cio_chat.py), Google GenAI) — real per-call cost.
- This cost asymmetry must be reflected in metering (weight expensive endpoints higher).

---

## 3. Design

### 3.1 Cost Weighting (Credits)

Don't meter "1 request = 1 unit." Assign a **credit cost per endpoint** so heavy endpoints consume more:

| Endpoint group | Suggested credits | Rationale |
|---|---|---|
| Cache reads (`/api/trades`, `/api/summary`, `/api/financials/*`, `/api/documents/*`) | 1 | DB read only |
| Lazy-fetch-triggering reads (cache miss path) | 2–5 | Triggers an upstream EDGAR fetch |
| `/api/transcript` | 10+ | Tavily paid call |
| `/api/filings/chat` | 20+ | LLM (Google GenAI) paid call, multi-agent |

> Tune the exact numbers against measured upstream costs (see [03](03_billing_and_pricing.md)). Define them in one place (`findata/server/billing/costs.py`).

### 3.2 Usage Table

```sql
CREATE TABLE usage_events (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    endpoint    TEXT NOT NULL,
    credits     INTEGER NOT NULL,
    status_code INTEGER NOT NULL,
    ts          TEXT NOT NULL          -- ISO8601 UTC
);
CREATE INDEX idx_usage_user_ts ON usage_events(user_id, ts);

-- Optional rollup for fast quota checks
CREATE TABLE usage_rollup (
    user_id     INTEGER NOT NULL,
    period      TEXT NOT NULL,         -- 'YYYY-MM' for monthly quota
    credits     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, period)
);
```

### 3.3 Metering Flow

```
Route handler completes ─▶ middleware/dependency records usage:
   - resolve endpoint → credits (from costs.py)
   - if user.plan == 'owner': skip (record optional, charge 0)
   - else: append usage_event + increment usage_rollup
```

- Prefer a **FastAPI middleware** (or response hook) so it captures the final status code and applies uniformly.
- Record **after** the handler so failed (5xx) calls can be excluded or discounted per policy.

### 3.4 Quota Enforcement

- Before/at request: check `usage_rollup[user, current_month] + cost <= plan_quota`.
- Over quota → **429** with a clear body (`{"error": "quota_exceeded", "reset": "<date>"}`).
- `plan='owner'` → unlimited (skip check).
- Plan→quota mapping lives next to pricing (`findata/server/billing/plans.py`).

### 3.5 Rate Limiting

- Separate from quota: protects the server and upstream (EDGAR 10 req/s, DART daily cap).
- Per-key token bucket (e.g. 5 req/s, burst 20). Simple in-memory bucket is fine for a single instance; use Redis if multi-instance.
- Over limit → **429** with `Retry-After`.
- **owner** exempt.
- This also doubles as upstream protection: cap how fast user traffic can trigger lazy fetches to EDGAR/DART (see [05](05_lazy_fetch_and_historical_backfill.md)).

---

## 4. Implementation Steps

1. [ ] **Cost & plan config**: `findata/server/billing/costs.py` (endpoint→credits), `findata/server/billing/plans.py` (plan→monthly quota, rate limit).
2. [ ] **Usage DB module**: `findata/server/db/usage_db.py` — `record_usage(user_id, endpoint, credits, status)`, `get_month_credits(user_id, period)`.
   - **Make it concurrency-safe**: do the `INSERT INTO usage_events` and the rollup increment in **one transaction**, using an atomic UPSERT — `INSERT INTO usage_rollup(user_id, period, credits) VALUES(?,?,?) ON CONFLICT(user_id, period) DO UPDATE SET credits = credits + excluded.credits`. Enable SQLite **WAL mode** so readers don't block the writer. (Simplest alternative: treat `usage_events` as the source of truth and compute the rollup with `SUM()` on read — no race at all, at the cost of a heavier query.)
3. [ ] **Metering middleware**: `findata/server/middleware/metering.py` — runs after handler, resolves credits, skips owner, writes usage.
4. [ ] **Quota dependency**: extend [auth.py](../../findata/server/auth.py) or new `quota.py` — pre-check monthly credits, raise 429 if exceeded (owner exempt).
5. [ ] **Rate limiter**: `findata/server/middleware/ratelimit.py` — per-key token bucket, owner exempt, `Retry-After` header.
6. [ ] **Wire into app**: register middleware in [app.py](../../findata/server/app.py); attach quota dependency to data routers.
7. [ ] **Usage endpoint (optional)**: `GET /api/usage` returning the caller's current period consumption (for a self-serve console).

> **Cross-cutting from [09](09_launch_readiness.md)**: the **cost & abuse guardrails (09 §3.5)** attach here — once the paid-upstream endpoints are metered, add the monthly budget alarm + circuit breaker so a single abuser can't run up your Google/Tavily bill. Reuse this plan's metering hook to drive them.

---

## 5. Files to Change/Create

- New: `findata/server/billing/costs.py`, `findata/server/billing/plans.py`
- New: `findata/server/db/usage_db.py`
- New: `findata/server/middleware/metering.py`, `findata/server/middleware/ratelimit.py`
- Edit: `findata/server/db/config.py` (usage tables can live in `accounts.db`)
- Edit: `findata/server/app.py` (register middleware), data routers (quota dependency)

---

## 6. Verification

- [ ] Authenticated normal user: each call appends a `usage_event` with the correct credits.
- [ ] Expensive endpoint (`/api/filings/chat`) records more credits than a cache read.
- [ ] Exceeding monthly quota → **429** with reset info; under quota → 200.
- [ ] Burst beyond rate limit → **429** with `Retry-After`.
- [ ] owner key: no quota/rate-limit enforcement; usage either skipped or recorded at 0 charge.

---

## 7. Pitfalls & Mitigations

Each pitfall is **prevented by a specific step in this plan**.

| Pitfall (what goes wrong) | How this plan prevents it |
|---|---|
| Metering and billing diverge → you lose money or overcharge | Steps 1–3 make metering the single source of truth; [03 Track A step 4 / Track B step 5](03_billing_and_pricing.md) reconcile provider charges against local `usage_events` |
| SQLite rollup increments race under load | Step 2: atomic UPSERT in one transaction + WAL mode (or compute the rollup from `usage_events` on read); migrate to Postgres ([07](07_storage_migration.md)) before serious traffic |
| Double-counting the lazy-fetch path | §3.1 + Step 1: a cache-miss request is **one** event at a higher credit weight, not two events |
| Confusing rate limit with quota | §3.4 vs §3.5 + Steps 4–5: implemented as two separate mechanisms (quota protects revenue, rate limit protects infra/upstream) |
| In-memory rate limit breaks across instances | §3.5 + Step 5: use Redis-backed buckets when running more than one instance ([08](08_deployment_and_infra.md)) |
