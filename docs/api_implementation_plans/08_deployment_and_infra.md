# 08 — Deployment & Infrastructure

> **Phase 3 / Order 8** (but read early — affects how 01–04 are wired)
> **Prerequisite**: [01_auth_and_api_keys.md](01_auth_and_api_keys.md) (self-exemption depends on topology)
> **Related**: [03_billing_and_pricing.md](03_billing_and_pricing.md), [04_form4_realtime_polling.md](04_form4_realtime_polling.md), [07_storage_migration.md](07_storage_migration.md)

---

## 1. Goal

- Deploy the API on AWS such that: regular users reach it **only through the billing gateway**, the **owner bypasses** it via a private path, and the **scheduled worker is separate** from the API.
- Manage secrets (upstream keys) safely.

---

## 2. Current State (Code-Grounded)

- App runs locally via `python -m findata.server.app` or `uvicorn findata.server.app:app` ([app.py](../../findata/server/app.py)); Windows event-loop policy is set for local dev.
- Secrets loaded from `.env` via `python-dotenv` ([core/config.py](../../findata/core/config.py), [db/config.py](../../findata/server/db/config.py)).
- No containerization, no scheduler infra, no gateway. Single-process, single-host assumed.

> **Clarification (from planning discussion)**: putting the app "on AWS" gives you **hosting/scaling** but **not** auth/quota/billing automatically. AWS API Gateway can issue keys + quotas but does **not** collect money — payment needs Stripe or AWS Marketplace. The closest to "it just handles everything end-to-end" is a managed marketplace like **RapidAPI**, not raw AWS (see [03](03_billing_and_pricing.md)).

---

## 3. Design

### 3.1 Topology

```
                 ┌──────────────────────────┐
 Regular users ─▶│ Billing gateway          │─┐   (public entry)
                 │ (RapidAPI / API GW)      │ │
                 └──────────────────────────┘ │
                                              ▼
                              ┌───────────────────────────┐
                              │ Origin API (private)       │  ← NOT publicly exposed
   Owner ──VPN/SSH/SG-allow──▶│ FastAPI on App Runner/ECS  │
                              └───────────────────────────┘
                                  │            │
                          ┌───────┘            └────────┐
                          ▼                             ▼
                    RDS (Postgres)                Scheduled worker
                    S3 (blobs)                    (EventBridge+Lambda
                    Redis (rate/locks)             or ECS scheduled task)
```

- **Origin is private**: only the gateway (via a shared secret header / VPC link / security group) and the owner's private path can reach it. This is the structural enforcement of self-exemption from [01 §3.1-A](01_auth_and_api_keys.md).
- **Worker separate**: the Form 4 poller ([04](04_form4_realtime_polling.md)) and scheduled ingestion ([06](06_scheduled_ingestion_and_freshness.md)) run as their own scheduled compute, writing to RDS/S3 — never inside the API request path.

### 3.2 Compute choice

| Choice | Fit |
|---|---|
| **AWS App Runner** | Easiest container hosting + autoscale; good first choice for the API. |
| **ECS Fargate** | More control, also hosts ECS scheduled tasks for the worker. |
| **Lambda** | Best for the polling worker (EventBridge cron); possible for API via adapter but App Runner/ECS is simpler for FastAPI. |

> Recommendation: **App Runner (API) + EventBridge+Lambda (worker)** for low ops, or **ECS Fargate** for both if you want one platform.

### 3.3 Secrets

- Move upstream keys (`OPEN_DART_API`, `GOOGLE_API_KEY`, `TAVILY_API_KEY`) from `.env` to **AWS Secrets Manager / SSM Parameter Store**; inject as env at runtime. `.env` stays for local dev only (it's already in `.gitignore`).
- The gateway↔Origin shared secret and `DATABASE_URL` also live in Secrets Manager.

### 3.4 Owner private path options

- VPN into the VPC, or SSH tunnel to the Origin host, or a security-group rule allowing only your IP to the Origin port. Any of these means your traffic never touches the gateway → $0.

---

## 4. Implementation Steps

1. [ ] **Containerize**: `Dockerfile` for the API (uvicorn/gunicorn). Note Playwright deps for `/api/download-pdf` ([api_10kq.py](../../findata/server/api/api_10kq.py)) — install browsers in the image or disable that endpoint server-side.
2. [ ] **Provision**: RDS (Postgres, [07](07_storage_migration.md)), S3 bucket, Redis (if multi-instance rate limiting), App Runner/ECS service.
3. [ ] **Secrets**: load upstream keys + `DATABASE_URL` + gateway secret from Secrets Manager.
4. [ ] **Lock down Origin**: no public ingress except the gateway (shared-secret header check in [auth.py](../../findata/server/auth.py) or infra-level VPC link/SG). Configure owner private path.
5. [ ] **Gateway**: put RapidAPI/API Gateway in front; map plans/pricing ([03](03_billing_and_pricing.md)).
6. [ ] **Worker deployment**: EventBridge cron → Lambda/ECS task running `form4_poller` ([04](04_form4_realtime_polling.md)) + scheduled ingestion ([06](06_scheduled_ingestion_and_freshness.md)). Gate in-process schedulers off in the API (`ENABLE_*_POLLER=0` on API, `=1` on worker).
7. [ ] **Initial universe pre-warm**: on first deploy, run a one-time bulk ingestion job for the **data universe** (S&P 500 + major KOSPI/KOSDAQ — defined in [06 §3.1](06_scheduled_ingestion_and_freshness.md)) so storage isn't cold. This prevents the first users from triggering mass on-demand EDGAR/DART fetches and hitting upstream rate limits. Run as a one-off ECS task / Lambda (or `python -m findata.server.ingestion.warmup`), separate from the recurring schedules. Idempotent (dedup) so it's safe to re-run.
8. [ ] **Health/observability**: `/health`, structured logs to CloudWatch, alarms on poller failures and 5xx rates.
9. [ ] **CI/CD**: build image → push to ECR → deploy.

> **Cross-cutting from [09](09_launch_readiness.md) — the terminal ops items land here**, since they need the infra to exist: **backup/DR (09 §3.7)** (RDS automated backups + S3 versioning), **monitoring/alerting (09 §3.9)** (extends step 8), and the **CI/test gate (09 §3.10)** (this step 9). Do these as part of deployment, before opening to traffic.

---

## 5. Files to Change/Create

- New: `Dockerfile`, `.dockerignore`, infra definitions (`infra/` — Terraform/CDK or console-documented), worker entrypoint/cron config, one-off warm-up entrypoint (`findata/server/ingestion/warmup.py`, driving the universe from [06](06_scheduled_ingestion_and_freshness.md)).
- Edit: [app.py](../../findata/server/app.py) (gateway-secret check, scheduler env gating, `/health`), `core/config.py` & `db/config.py` (secrets/`DATABASE_URL` from env).

---

## 6. Verification

- [ ] Public request directly to Origin (bypassing gateway) → **rejected** (no gateway secret / not reachable).
- [ ] Request through the gateway with a valid plan → **200**.
- [ ] Owner via private path → **200**, and **no** gateway/billing event recorded.
- [ ] Worker instance runs the poller; API instances do **not** (env gating verified).
- [ ] Secrets are injected at runtime; no keys in the image or repo.
- [ ] Killing the worker doesn't affect API serving (decoupling verified).

---

## 7. Pitfalls & Mitigations

Each pitfall is **prevented by a specific step in this plan**.

| Pitfall (what goes wrong) | How this plan prevents it |
|---|---|
| "Deploy to AWS" ≠ billing handled | Step 5: explicitly put the billing gateway in front ([03](03_billing_and_pricing.md)) |
| Publicly reachable Origin defeats billing | Step 4: no public ingress except the gateway (shared secret / VPC link / SG) |
| Owner path leaking through the gateway → you pay your own margin | Step 4 + §6 Verification: owner reaches Origin only via the private path, explicitly tested |
| Schedulers running on API instances double-ingest & contend | Step 6: `ENABLE_*_POLLER=0` on API, `=1` on the single worker |
| Playwright in containers is heavy / breaks | Step 1: install browser deps in the image or disable `/api/download-pdf` server-side |
| Cold-cache deploy → first-user fetch stampede hits EDGAR/DART limits | Step 7: pre-warm the universe before opening to traffic |
| In-process rate-limit/single-flight state is per-instance | Externalize to Redis once you run >1 API instance ([02](02_metering_and_rate_limiting.md), [07](07_storage_migration.md)) |
