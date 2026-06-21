# 09 — Launch Readiness (Commercial Service Gaps)

> **Phase 1–3 cross-cutting** (start the 🔴 items before public launch)
> **Prerequisite**: [01_auth_and_api_keys.md](01_auth_and_api_keys.md), [02_metering_and_rate_limiting.md](02_metering_and_rate_limiting.md), [03_billing_and_pricing.md](03_billing_and_pricing.md)
> **Related**: [08_deployment_and_infra.md](08_deployment_and_infra.md)

---

## 1. Goal

Plans 01–08 cover the **technical architecture** of the paid API. This doc covers the remaining **"real commercial service"** concerns — mostly operational/legal/product items, plus a few technical gaps — that 01–08 intentionally left out. Without the 🔴 items below, "other users sign up and pay" does not actually work end-to-end.

> **Severity legend**: 🔴 required before public launch · 🟡 needed soon after · 🟢 hardening / nice-to-have.

> **How to use this doc — read this first.** 09 is **not** a final phase you do all at once after 01–08, and it is **not** fully dissolved into the other plans either. It is a **launch-readiness checklist** where each item has a designated time and home:
> - **Structural items** (versioning §3.3, error contract §3.4, signup decision §3.1, cost guardrails §3.5) must be **folded into 01–03 as you build them** — retrofitting them later is a breaking change.
> - **Terminal items** (legal §3.2, docs §3.6, backup/DR §3.7, monitoring §3.9, CI §3.10) are done **once, near launch**, after the infra exists.
>
> See the timing map in §4. The relevant earlier plans now carry a "Cross-cutting from [09]" pointer so the structural items aren't missed while implementing them.

---

## 2. Current State (Code-Grounded)

- Key issuance is **admin-only** (`python -m findata.server.tools.issue_key`, see [01 §4](01_auth_and_api_keys.md)) — there is **no self-serve signup/checkout** for users to obtain a key themselves.
- No Terms of Service, Privacy Policy, or data-redistribution review. Upstream data comes from SEC (public), OpenDART (`OPEN_DART_API`), Tavily, and Google GenAI — each has its own terms.
- No API versioning: routes are unversioned (`/api/...` in [findata/server/api/](../../findata/server/api/)), no `/v1/`.
- Error responses are ad hoc (some `HTTPException` in routers, 429 added in [02](02_metering_and_rate_limiting.md)) — no unified error schema.
- Public docs: only FastAPI's auto `/docs`; no published/versioned developer documentation.
- No upstream cost ceiling / budget alarm; rate limits exist ([02](02_metering_and_rate_limiting.md)) but not a monthly $ cap or circuit breaker on Google/Tavily spend.
- No backup/DR policy (SQLite files today; RDS backups to be configured in [07](07_storage_migration.md)).
- A `tests/` directory exists but there is no CI gate tied to these plans.

---

## 3. The Gaps

### 🔴 3.1 Self-serve Signup, Checkout & Key Management

The single most important launch blocker. Decide the path early because it changes a lot of work:

| Path | Who provides signup/checkout/key UI | Effort |
|---|---|---|
| **Managed gateway (RapidAPI etc.)** | The provider does signup, payment, and key issuance for you | Low — recommended for launch ([03 Track A](03_billing_and_pricing.md)) |
| **Direct (Stripe)** | You build: signup, Stripe Checkout, a key-management console, password/OAuth | High |

- If managed: your `accounts`/`api_keys` model from [01](01_auth_and_api_keys.md) may be partly delegated to the gateway; keep local records for reconciliation only.
- If direct: you need a minimal web console (signup → Stripe Checkout → create key → show once → revoke/rotate) on top of the [01](01_auth_and_api_keys.md) data model and the [03 Track B](03_billing_and_pricing.md) billing.

### 🔴 3.2 Legal & Data Redistribution Rights

- **Terms of Service** + **Privacy Policy** (you store user email + usage; privacy law applies).
- **Data redistribution review** — confirm you may *commercially resell* derived data:
  - SEC EDGAR: public domain, fine (respect fair-access / User-Agent rules).
  - **OpenDART**: review its terms for commercial redistribution.
  - **Tavily / Google GenAI**: review terms for reselling generated/derived output.
- **Financial disclaimer**: "for informational purposes only, not investment advice," accuracy/"as-is" disclaimer — important when selling financial data.

### 🟡 3.3 API Versioning

- Prefix routes with `/v1/` and define a deprecation policy (sunset headers, advance notice).
- Lets you change response shapes later without breaking paying customers.

### 🟡 3.4 Unified Error Contract

- One error schema across all endpoints: `{ "error": <code>, "message": <human>, "detail": <optional> }`.
- Consistent status codes: 400 (bad input), 401 (no/invalid key — [01](01_auth_and_api_keys.md)), 403 (plan not allowed), 404 (not found), 429 (quota/rate — [02](02_metering_and_rate_limiting.md)), 5xx (upstream/internal).
- A FastAPI exception handler centralizes this.

### 🟡 3.5 Cost & Abuse Guardrails

- **Monthly upstream budget alarm** on Google GenAI / Tavily spend (the paid-upstream endpoints, [00 §3](00_overview.md)).
- **Circuit breaker**: if upstream spend or error rate crosses a threshold, degrade `/api/filings/chat` and `/api/transcript` (return 503 / cached-only) instead of bleeding money.
- Per-key anomaly detection (sudden spikes) beyond the basic rate limit.

### 🟡 3.6 Public Developer Docs

- Published, versioned docs (beyond auto `/docs`): auth/key usage, per-endpoint examples, rate-limit/quota explanation, error codes, changelog.
- Quickstart + a sample request for each endpoint.

### 🟢 3.7 Backup / Disaster Recovery

- Enable RDS automated backups + point-in-time recovery; define retention ([07](07_storage_migration.md), [08](08_deployment_and_infra.md)).
- S3 versioning/lifecycle for raw blobs.
- Document a restore runbook.

### 🟢 3.8 Security Hardening

- Input validation on all query params (lengths, enums, ticker format).
- Review SQL construction in [api_form4.py](../../findata/server/api/api_form4.py) etc. — values are parameterized today; ensure no user input reaches f-string SQL as table/column identifiers.
- Secret rotation policy for upstream keys + gateway secret (Secrets Manager, [08 §3.3](08_deployment_and_infra.md)).
- Standard headers (HSTS, no server banner), dependency vulnerability scanning.

### 🟢 3.9 Monitoring, Alerting & Status

- Uptime monitoring + alerting (5xx rate, latency, poller failures — extends [08 §4 step 8](08_deployment_and_infra.md)).
- A public status page (optional but expected for a paid API).
- Define a target availability (informal SLO is fine at first).

### 🟢 3.10 CI / Test Gate

- Wire the existing `tests/` into CI (build → test → deploy, [08 §4](08_deployment_and_infra.md)).
- Add contract tests for the auth/quota/error behavior introduced in [01](01_auth_and_api_keys.md)/[02](02_metering_and_rate_limiting.md).

---

## 4. When & How to Implement

### 4.1 Timing map (when each item happens relative to plans 01–08)

| 09 item | When | Fold into / attach to |
|---|---|---|
| §3.3 API versioning (`/v1/`) | **Earliest** — the first time you touch `app.py`/routers | Build it into [01](01_auth_and_api_keys.md), apply to every router after |
| §3.4 Unified error contract | Early — before many endpoints exist | Set up during [01](01_auth_and_api_keys.md)/[02](02_metering_and_rate_limiting.md) |
| §3.1 Self-serve signup | **Decide** in Phase 1; implement alongside auth + billing | With [01](01_auth_and_api_keys.md) + [03](03_billing_and_pricing.md) |
| §3.5 Cost & abuse guardrails | As soon as paid-upstream endpoints are metered | With [02](02_metering_and_rate_limiting.md) + [03](03_billing_and_pricing.md) |
| §3.2 Legal & data rights | Start **now** in parallel (non-code); must finish before public launch | Standalone (legal) |
| §3.7 Backup / DR | When the infra exists | With [07](07_storage_migration.md) + [08](08_deployment_and_infra.md) |
| §3.9 Monitoring / alerting | With deployment | With [08](08_deployment_and_infra.md) |
| §3.10 CI / test gate | With the deploy pipeline (ideally early) | With [08](08_deployment_and_infra.md) |
| §3.8 Security hardening | Continuous; final pass before launch | Cross-cutting |
| §3.6 Public developer docs | After the API surface stabilizes, before launch | Terminal (near launch) |

> **Rule of thumb**: bake the structural items (3.1, 3.3, 3.4, 3.5) in while building 01–03; do the terminal items (3.2, 3.6, 3.7–3.10) once near launch. This doc is the checklist that guarantees none are forgotten.

### 4.2 Execution checklist (suggested order for 09's own remaining work)

1. [ ] **Decide signup path (3.1)** — managed gateway vs direct. This unblocks everything else. (Managed recommended for launch.)
2. [ ] **Legal (3.2)** — draft ToS, Privacy Policy, disclaimer; confirm OpenDART/Tavily/Google redistribution rights. (Non-code; start in parallel.)
3. [ ] **Versioning (3.3)** — introduce `/v1/` before exposing to external users (cheap to do early, painful later).
4. [ ] **Error contract (3.4)** — central exception handler + documented codes.
5. [ ] **Cost guardrails (3.5)** — budget alarms + circuit breaker on paid-upstream endpoints.
6. [ ] **Public docs (3.6)** — quickstart + per-endpoint examples + error reference.
7. [ ] **Backup/DR (3.7)**, **security (3.8)**, **monitoring (3.9)**, **CI (3.10)** — harden once the above is live.

---

## 5. Files to Change/Create

- New: `findata/server/errors.py` (exception handler + error schema), `findata/server/middleware/circuit_breaker.py`
- New (direct path only): minimal signup/console app + `findata/server/api/api_account.py`
- New (docs/legal): `TERMS.md`, `PRIVACY.md`, `DISCLAIMER.md`, published API docs
- Edit: [app.py](../../findata/server/app.py) (mount routers under `/v1`, register error handler), routers (versioned paths, validation)
- Config/infra: budget alarms, RDS backup, CI pipeline ([08](08_deployment_and_infra.md))

---

## 6. Verification

- [ ] A brand-new external user can sign up, pay, and get a working key **without you manually running a CLI** (3.1).
- [ ] ToS/Privacy/Disclaimer are linked from the docs and accepted at signup (3.2).
- [ ] All endpoints respond under `/v1/...`; old unversioned paths handled per policy (3.3).
- [ ] Every error path returns the unified schema with the correct status code (3.4).
- [ ] Simulated upstream-spend spike trips the circuit breaker / fires the budget alarm (3.5).
- [ ] A new developer can call each endpoint using only the public docs (3.6).
- [ ] RDS restore from backup succeeds in a test (3.7); CI blocks a failing test from deploying (3.10).

---

## 7. Pitfalls & Mitigations

Each pitfall is **prevented by a specific step in this plan**.

| Pitfall (what goes wrong) | How this plan prevents it |
|---|---|
| Self-serve signup missing → can't onboard payers at scale | §3.1 + Step 1: choose a managed gateway (provider handles signup/pay/keys) or build the direct console — decided **before** building billing UI |
| Skipping the data-rights review → non-compliant business | §3.2 + Step 2: review OpenDART/Tavily/Google resale terms early; it may constrain which endpoints you can resell |
| Adding `/v1/` after customers integrate = breaking change | §3.3 + Step 3: introduce versioning **before** public exposure |
| No upstream cost ceiling → one abuser runs up your Google/Tavily bill | §3.5 + Step 5: budget alarm + circuit breaker on paid-upstream endpoints |
| Treating this doc as "later" | Step order: 🔴 items (3.1, 3.2) gate launch; only 🟢 items are genuinely deferrable |
