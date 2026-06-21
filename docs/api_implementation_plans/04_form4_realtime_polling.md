# 04 — Form 4 Market-Wide Realtime Polling Worker

> **Phase 2 / Order 4**
> **Prerequisite**: None strictly, but deploy alongside [08_deployment_and_infra.md](08_deployment_and_infra.md) (worker/API split)
> **Related**: [05_lazy_fetch_and_historical_backfill.md](05_lazy_fetch_and_historical_backfill.md), [06_scheduled_ingestion_and_freshness.md](06_scheduled_ingestion_and_freshness.md)

---

## 1. Goal

- Continuously capture **every company's** newest Form 4 filings so the API can serve near-realtime insider trading data — at low cost.
- Run this as a **scheduled worker separate from the API server** so fetch load never delays user responses.

---

## 2. Current State (Code-Grounded)

Building blocks exist; the scheduler does not.

- `parse_all_from_rss()` — fetches the market-wide latest ~100 Form 4s from the EDGAR `getcurrent` Atom feed ([findata/sec/utils/form4/form4_parser.py](../../findata/sec/utils/form4/form4_parser.py), and the raw feed pattern in [sec_form4_rss.py](../../findata/sec/utils/form4/sec_form4_rss.py)).
- `save_to_db(filings, db_path)` returns `(inserted, skipped)` → **dedup (diff) is already built in** ([findata/server/db/form4_db.py](../../findata/server/db/form4_db.py)).
- `POST /api/refresh?source=all` runs `parse_all_from_rss()` + `save_to_db()` **manually** ([findata/server/api/api_form4.py](../../findata/server/api/api_form4.py)).
- ❌ **Missing**: a scheduler that runs this every ~10 minutes automatically.

---

## 3. Design

### 3.1 Cost Reality (why this is cheap)

- The **feed poll itself is ~free**: one HTTP GET every 10 min = 144 requests/day vs EDGAR's 10 req/s limit. Compute is trivial (fits AWS Lambda free tier).
- The **real cost is processing new filings** — bounded by the number of *new* filings, not the poll frequency. So:
  - **diff/dedup** (already in `save_to_db`) is the key cost lever — process only the ~few new ones each cycle, discard the ~95 already seen.
  - Lowering poll frequency saves almost nothing; dedup saves everything.

### 3.2 Worker Loop

```
Every 10 minutes (scheduled, separate process):
  1. parse_all_from_rss()              # 1 GET, market-wide latest ~100
  2. save_to_db(filings, insider_all)  # dedup by accession → only new rows persist
  3. log inserted/skipped counts
Once per day (reconciliation):
  4. Pull EDGAR daily index (form.idx) → catch filings that rolled off the 100-entry feed
     during high-volume periods → save_to_db (dedup)
```

### 3.3 Where to Run

Three viable options (pick per [08](08_deployment_and_infra.md)):

| Option | Fit |
|---|---|
| **AWS EventBridge (cron) + Lambda** | Cheapest, fully decoupled. Best if the worker logic is importable standalone. |
| **ECS scheduled task** | Good if you already containerize the app. |
| **In-container background scheduler** (APScheduler) | Simplest to start, but couples worker to API process — acceptable for MVP, migrate later. |

> Recommendation: start with an **in-process scheduler (APScheduler)** for the MVP if running a single container, then extract to **EventBridge+Lambda** when separating worker from API.

### 3.4 Decoupling from the API

- The worker **writes** to the Form 4 store; the API only **reads**. Never run the polling loop inside a request handler.
- With SQLite this means writer/reader on the same file — fine at low volume, but a reason to move to Postgres ([07](07_storage_migration.md)) as traffic grows.

---

## 4. Implementation Steps

1. [ ] **Extract the cycle into a callable**: `findata/server/ingestion/form4_poller.py` with `run_market_poll()` that calls `parse_all_from_rss()` + `save_to_db(..., INSIDER_ALL_DB)` and logs `(inserted, skipped)`.
2. [ ] **Add the scheduler**:
   - MVP: register an APScheduler job (every 10 min) on app startup in [app.py](../../findata/server/app.py), guarded by an env flag (`ENABLE_FORM4_POLLER=1`) so only the worker instance runs it.
   - Or: an entrypoint `python -m findata.server.ingestion.form4_poller --loop 600` for EventBridge/ECS.
3. [ ] **Daily reconciliation**: `reconcile_daily_index(date)` that downloads EDGAR's daily index, filters Form 4, and `save_to_db` (dedup). Schedule once/day.
4. [ ] **Observability**: structured logs + a simple counter (filings ingested/day); optional `GET /api/health/poller` showing last successful run.
5. [ ] **Respect SEC etiquette**: correct `User-Agent` (name + email — note [sec_form4_rss.py](../../findata/sec/utils/form4/sec_form4_rss.py) still has the placeholder `YourName your.email@example.com`; fix before production), and keep per-request delay for any fan-out fetches.

---

## 5. Files to Change/Create

- New: `findata/server/ingestion/form4_poller.py` (`run_market_poll`, `reconcile_daily_index`)
- Edit: `findata/server/app.py` (optional APScheduler job behind env flag)
- Edit: `findata/sec/utils/form4/sec_form4_rss.py` (real `User-Agent`)
- Config: scheduler/cron definition in deploy ([08](08_deployment_and_infra.md))

---

## 6. Verification

- [ ] Start the worker; after one cycle, new Form 4 rows appear in `insider_all.db` with `inserted > 0`.
- [ ] Second cycle with no new market filings → `inserted == 0`, `skipped > 0` (dedup works).
- [ ] `/api/trades?source=all` returns the freshly polled data.
- [ ] Kill and restart worker → no duplicate rows (accession dedup).
- [ ] Daily reconciliation backfills a filing that was absent from the 100-entry feed.
- [ ] Poller failure (network error) is logged and the loop continues next cycle.

---

## 7. Pitfalls & Mitigations

Each pitfall is **prevented by a specific step in this plan**.

| Pitfall (what goes wrong) | How this plan prevents it |
|---|---|
| Polling less often to "save cost" (wrong lever) | §3.1: cost is in new-filing processing (controlled by dedup, Step 1), not poll frequency — keep the 10-min cadence |
| Feed roll-off drops filings during busy periods | Step 3: daily index reconciliation backfills anything missed by the 100-entry feed |
| Scheduler running in every API instance → duplicate polls + write contention | Step 2 + [08 step 6](08_deployment_and_infra.md): gate behind `ENABLE_FORM4_POLLER`, run on one worker only |
| Placeholder User-Agent → SEC blocks you | Step 5: set a real `User-Agent` (name + email) before production |
| SQLite write contention (poller vs readers) | Acknowledged limit → migrate to Postgres ([07](07_storage_migration.md)) as traffic grows |
| Missing historical data | By design this worker is forward-only; history is covered by [05](05_lazy_fetch_and_historical_backfill.md) |
