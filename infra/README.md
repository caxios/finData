# Infrastructure & Deployment Runbook (plan 08)

> Implements [docs/api_implementation_plans/08_deployment_and_infra.md](../docs/api_implementation_plans/08_deployment_and_infra.md).
> The repo ships the deployable artifacts (Dockerfile, worker entrypoint, CI,
> env-driven config). The AWS resources below are **console/IaC-provisioned** —
> this is the runbook + the exact knobs the app reads. (Terraform/CDK can be
> added later; the app needs no code change to move to AWS — it's all env vars.)

---

## 1. Topology

```
 Regular users ──(client key)──▶ Billing gateway (RapidAPI / API Gateway)
                                        │  injects X-Gateway-Secret
                                        ▼
 Owner ──(VPN / SG-allow, private)──▶ Origin API  (App Runner / ECS Fargate)   ← NOT public
                                        │
                 ┌──────────────────────┼───────────────────────┐
                 ▼                      ▼                        ▼
            RDS (Postgres)          S3 (blobs)            Worker (ECS task / Lambda)
            DATABASE_URL            raw filings/PDFs      form4 poll + scheduled ingest
            (plan 07 cut-over)                            ENABLE_FORM4_POLLER=1
            ElastiCache Redis (multi-instance rate-limit / locks — plan 07 Step 8)
```

- **Origin is private.** Only the gateway (carrying `X-Gateway-Secret`) and the
  owner's private path reach it. Enforced in code by `require_gateway`
  ([findata/server/auth.py](../findata/server/auth.py)) **and** at the network
  layer (private subnet + security group / VPC link). Defense in depth.
- **Owner = $0** by going around the gateway (self-exemption A): connect over
  VPN / an SG rule allowing only your IP to the Origin port, with an `owner`-plan
  key. `require_gateway` exempts `plan=owner`, and metering/quota already exempt
  owner — so no billing event is ever recorded.

---

## 2. Compute

| Role | Service | Command |
|---|---|---|
| API | App Runner (or ECS Fargate) | `uvicorn findata.server.app:app --host 0.0.0.0 --port 8000` (image default) |
| Worker | ECS scheduled/long task (or EventBridge→Lambda) | `python -m findata.server.worker` |
| Warm-up | one-off ECS task / `docker run` | `python -m findata.server.ingestion.warmup` |

One image (`Dockerfile`) serves all roles; the **command** selects the role.

### Worker scheduling
The worker process runs the Form 4 poller (~10 min) + scheduled financials/DART
refresh (daily) itself (see [findata/server/worker.py](../findata/server/worker.py)).
Alternative fully-decoupled option: EventBridge cron → Lambda/ECS task invoking
`python -m findata.server.ingestion.form4_poller --reconcile` and
`python -m findata.server.ingestion.scheduled --once` on their own cadences.

> **Gating:** the API containers must have `ENABLE_FORM4_POLLER` /
> `ENABLE_SCHEDULED_INGESTION` **unset** (default off). Only the worker runs them.
> Running them in every API replica would double-ingest and contend on writes.

---

## 3. Secrets (AWS Secrets Manager / SSM)

Move these out of `.env` (local dev only) and inject as env at runtime:

- `OPEN_DART_API`, `GOOGLE_API_KEY`, `TAVILY_API_KEY` — upstream provider keys.
- `FINDATA_GATEWAY_SECRET` — shared secret the gateway sends as `X-Gateway-Secret`.
- `DATABASE_URL` — once Postgres is cut over (plan 07).
- (Stripe keys later, if Track B — plan 03.)

App Runner: configure as runtime env from Secrets Manager. ECS: `secrets:` in the
task definition. Never bake secrets into the image (`.env` is in `.dockerignore`).

---

## 4. Environment variable matrix

| Variable | API | Worker | Notes |
|---|---|---|---|
| `FINDATA_DATA_DIR` | ✅ | ✅ | Shared storage (EFS) while on SQLite; irrelevant once on RDS/S3 |
| `DATABASE_URL` | ✅ | ✅ | Postgres (plan 07); unset = SQLite |
| `FINDATA_GATEWAY_SECRET` | ✅ | — | Enforce gateway-only access |
| `FINDATA_CORS_ORIGINS` | ✅ | — | Lock to your console/frontend domains |
| `FINDATA_UPSTREAM_MONTHLY_BUDGET_USD` | ✅ | — | Circuit breaker on paid endpoints |
| `ENABLE_FORM4_POLLER` | `0` | `1` | Single-writer gate |
| `ENABLE_SCHEDULED_INGESTION` | `0` | `1` | Single-writer gate |
| `ENABLE_PDF_DOWNLOAD` | `0` | — | Needs Playwright/Chromium image |
| `OPEN_DART_API`/`GOOGLE_API_KEY`/`TAVILY_API_KEY` | ✅ | ✅ | From Secrets Manager |
| `FINDATA_SEC_USER_AGENT` | ✅ | ✅ | SEC requires name + email |

---

## 5. Data stores

- **RDS (Postgres)** — structured rows. Enable **automated backups +
  point-in-time recovery** (09 §3.7). Set `DATABASE_URL` once cut over (plan 07).
- **S3** — raw filing docs / PDFs; enable **versioning + lifecycle** (09 §3.7).
- **ElastiCache Redis** — only when running >1 API replica: externalize the
  in-process rate-limit buckets and single-flight locks (plan 07 Step 8). Until
  then, run a single API replica so the in-memory limiter is correct.

---

## 6. Observability (09 §3.9)

- `/health` (liveness) and `/api/health/poller` (last poll, failures) — both
  unauthenticated. Point the load balancer / App Runner health check at `/health`.
- Ship container logs to **CloudWatch** (structured stdout already in place).
- Alarms: 5xx rate, p95 latency, and **poller failure** (alert when
  `/api/health/poller` `consecutive_failures` climbs or `last_success_ts` is stale).
- Budget alarm on Google/Tavily spend backstops the in-app circuit breaker.

---

## 7. CI/CD (09 §3.10)

[.github/workflows/ci.yml](../.github/workflows/ci.yml): on PR/push → install +
`pytest` (test gate) → `docker build`. On `main`, extend with: push image to ECR
and roll the App Runner/ECS service (commands sketched in the workflow).

---

## 8. First-deploy order

1. Provision RDS, S3, (Redis), Secrets, the API service, and the worker.
2. Put secrets in Secrets Manager; wire env per the matrix above.
3. Deploy the image; confirm `/health` is green.
4. **Warm up the universe** (one-off): `python -m findata.server.ingestion.warmup`
   — prevents a cold-cache stampede on first traffic (plan 08 Step 7 / 06 §3.1).
5. Put the gateway in front; map plans/pricing (plan 03); set `FINDATA_GATEWAY_SECRET`.
6. Verify the checklist below, then open to traffic.

---

## 9. Verification checklist (plan 08 §6)

- [ ] Public request **directly** to Origin (no `X-Gateway-Secret`, non-owner key) → **403**.
- [ ] Request **through the gateway** (valid plan) → **200**.
- [ ] **Owner** via private path (owner key, no gateway secret) → **200**, no billing event.
- [ ] Worker runs the poller (`/api/health/poller` advancing); API replicas do **not** (gating).
- [ ] Secrets injected at runtime; none in the image or repo (`.dockerignore` excludes `.env`).
- [ ] Killing the worker does not affect API serving (decoupled).
