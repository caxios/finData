# Commercial API Implementation Plans — Overview (INDEX)

> **Version**: 0.1.0
> **Date**: 2026-06-21
> **Purpose**: A set of feature-by-feature implementation plans for turning the `findata` project into a commercial API where "I (the developer) use it for free, and every other user pays a margin-loaded fee."
> **How to use**: Each `NN_*.md` file in this folder is an independent implementation unit. The implementer (human or AI) should follow the **Implementation Order** below and work through them one at a time. Each doc is structured as "Current State (grounded in code) → Design → Step-by-step Implementation → Verification."

---

## 1. Business Goals

1. **I (the developer) use my own API for free.** My key / my path never goes through the billing layer.
2. **Everyone else pays a margin-loaded fee.** Authenticate → meter usage → bill.

These two goals are achieved **not** with a code branch (`if user == me`) but with **network path separation + a new billing layer** (see [01_auth_and_api_keys.md](01_auth_and_api_keys.md)).

---

## 2. Key Concept — There Are Two Kinds of "Keys"

This is the most common point of confusion when commercializing this project. Always distinguish:

| | (A) Upstream keys | (B) Client keys |
|---|---|---|
| Definition | Keys the **server** uses to fetch **source data** | Keys a **user** uses to call **our API** |
| Examples | `OPEN_DART_API`, `GOOGLE_API_KEY`, `TAVILY_API_KEY` | The `fd_live_xxx`-style keys we will issue |
| Location | Server env vars only (.env / Secrets Manager) | Issued to users, stored hashed in DB (`api_keys`) |
| Current state | ✅ Already in use ([findata/dart/client.py:117](../../findata/dart/client.py), [findata/sec/const.py:5](../../findata/sec/const.py)) | ❌ **Does not exist — to be built** |

> **(A) always uses my key regardless of who calls.** So "I use my own key" is already automatically true. The only thing we build is **(B) client keys + a billing layer.**

---

## 3. Cost Structure — Per-Endpoint Marginal Cost Differs

The foundation for margin/pricing design. Endpoints fall into two classes:

| Class | Endpoints | Marginal cost (per request) |
|---|---|---|
| **Cache-serving** | `/api/trades`, `/api/summary`, `/api/documents/*`, `/api/financials/*`, etc. | ~0 (DB read + fixed server cost) |
| **Paid-upstream-calling** | `/api/transcript` (Tavily), `/api/filings/chat` (Google GenAI) | Real per-call charge |

→ Price cache-serving endpoints with **quota/flat tiers**, and paid-upstream endpoints with **per-call metering** (see [03_billing_and_pricing.md](03_billing_and_pricing.md)).

---

## 4. Target Architecture (At a Glance)

```
                         ┌─────────────────────────────────────┐
   Regular user ─(client key)─▶│  Billing gateway                     │
                         │  (auth · quota · metering · payment) │──┐
                         └─────────────────────────────────────┘  │
                                                                   ▼
   Me (developer) ──(private path: VPN/SSH/localhost, bypass gate)──▶ Origin API server (FastAPI)
                                                                   │
                                                   ┌───────────────┼───────────────┐
                                                   ▼               ▼               ▼
                                            RDS (Postgres)        S3 (raw)      Scheduled worker
                                            structured data       filings       (form4 10-min poll,
                                                                                financials daily/weekly)
```

- **Billing gateway**: Start with a managed provider (e.g. RapidAPI), then move to direct Stripe integration to widen margin.
- **My free usage**: Don't expose Origin directly; I connect via a private path → physically bypass the gate.
- **Scheduled worker**: A separate process from the API server so fetch load never affects user response latency.
- **Data universe**: Don't pre-load all of EDGAR/DART at deploy time. Define a bounded **universe** (e.g. S&P 500 + major KOSPI/KOSDAQ names) to eagerly warm and keep fresh; everything else is served lazily on demand. Detail in [06_scheduled_ingestion_and_freshness.md §3.1](06_scheduled_ingestion_and_freshness.md); the one-time deploy warm-up is in [08_deployment_and_infra.md](08_deployment_and_infra.md).

---

## 5. Current Code State (Implementation Starting Point)

| Area | Current state |
|---|---|
| Authentication | ❌ None. `CORSMiddleware(allow_origins=["*"])`, no auth → **deploying now means anyone calls free & unlimited** ([findata/server/app.py](../../findata/server/app.py)) |
| Usage metering | ❌ None |
| Billing | ❌ None |
| Form4 lazy fetch → store → reuse | ✅ Implemented (`/api/trades` + `_lazy_load`, [findata/server/api/api_form4.py](../../findata/server/api/api_form4.py)) |
| Form4 market-wide ingest building blocks | ✅ `parse_all_from_rss()` + `POST /api/refresh` + `save_to_db` (dedup built in) |
| Form4 10-min auto polling | ❌ Building blocks exist but **no scheduler** |
| Form4 historical-period backfill | ❌ Not supported (lazy fetch is "recent N" only, no date range) |
| Financials / 10-K·Q batch ingest | △ Manual run scripts exist ([ingestion/](../../findata/server/ingestion/)), no auto schedule |
| Storage | SQLite (`~/.findata/sec_db/*.db`) — weak for multi-user concurrent writes |
| Cache freshness (TTL) | △ Partial in `company_data.py` (10-K/Q 90 days, Form4 7 days) |

---

## 6. Implementation Order (Recommended)

Ordered by dependency. Each step is a standalone document.

### Phase 1 — Minimum for Commercialization (required before deploy)
1. [01_auth_and_api_keys.md](01_auth_and_api_keys.md) — Client key issuance/validation, self-exemption
2. [02_metering_and_rate_limiting.md](02_metering_and_rate_limiting.md) — Usage metering, quotas, rate limits
3. [03_billing_and_pricing.md](03_billing_and_pricing.md) — Billing/margin (managed-first)

### Phase 2 — Data Reliability / Realtime
4. [04_form4_realtime_polling.md](04_form4_realtime_polling.md) — Market-wide 10-min auto polling worker
5. [05_lazy_fetch_and_historical_backfill.md](05_lazy_fetch_and_historical_backfill.md) — Lazy fetch cleanup + new historical-period backfill
6. [06_scheduled_ingestion_and_freshness.md](06_scheduled_ingestion_and_freshness.md) — Scheduled financials/filings refresh + freshness policy

### Phase 3 — Operational Scaling
7. [07_storage_migration.md](07_storage_migration.md) — SQLite → RDS (Postgres) + S3
8. [08_deployment_and_infra.md](08_deployment_and_infra.md) — AWS deployment topology, worker/API split, secrets

### Cross-cutting — Launch Readiness
9. [09_launch_readiness.md](09_launch_readiness.md) — Commercial gaps beyond the core architecture: self-serve signup, legal/data rights, API versioning, error contract, cost guardrails, backup/DR, docs. **This is a launch checklist, not a final phase** — each item has a timing (see [09 §4 timing map](09_launch_readiness.md)): structural items (versioning, error contract, signup, cost guardrails) fold into 01–03 as you build them; terminal items (legal, docs, backup/DR, monitoring, CI) are done once near launch. The relevant plans (01, 02, 03, 08) carry "Cross-cutting from 09" pointers.

> **Fast MVP**: Phase 1 (1→2→3) + [04](04_form4_realtime_polling.md) alone is enough to launch a "near-realtime insider-trading paid API." Storage migration (07) can wait until traffic grows. But before opening to **paying outside users**, clear the 🔴 items in [09](09_launch_readiness.md) (self-serve signup + legal/data-redistribution rights).

---

## 7. Document Convention (Common Template for Each Plan)

Each `NN_*.md` contains these sections:

1. **Goal** — what this feature achieves (1–2 sentences)
2. **Current State** — related code/files with real paths and line numbers
3. **Design** — data structures, flow, options, recommendation
4. **Implementation Steps** — ordered checklist (each step a standalone commit unit)
5. **Files to Change/Create** — affected files
6. **Verification** — how to confirm behavior
7. **Dependencies** — prerequisite plans
8. **Pitfalls** — easy-to-miss points

---

## 8. Glossary

- **cache-aside (lazy loading)**: Check storage first on request; if missing, fetch from source, store, then respond.
- **diff / dedup**: Compare newly fetched data against what we already have (unique ID = accession number) and process only the new items.
- **watchlist filter**: Keep only tracked tickers (CIKs) from a market-wide feed.
- **self-exemption**: The mechanism that keeps the developer from going through the billing layer.
- **getcurrent / getcompany**: The two modes of the EDGAR Atom feed. The former is market-wide latest, the latter is a single company's history.
- **data universe**: The bounded set of companies (e.g. S&P 500 + major KOSPI/KOSDAQ) that is eagerly pre-warmed and kept fresh on a schedule, as opposed to the long tail served lazily on demand. See [06 §3.1](06_scheduled_ingestion_and_freshness.md).
- **pre-warm (warm-up)**: A one-time bulk ingestion run at initial deploy that populates storage for the universe so users don't trigger mass on-demand fetches from a cold cache.
