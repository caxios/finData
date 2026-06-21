# 06 — Scheduled Ingestion & Cache Freshness

> **Phase 2 / Order 6**
> **Prerequisite**: None (extends existing ingestion scripts)
> **Related**: [04_form4_realtime_polling.md](04_form4_realtime_polling.md), [05_lazy_fetch_and_historical_backfill.md](05_lazy_fetch_and_historical_backfill.md)

---

## 1. Goal

- Keep **financials and filings** (10-K/10-Q, DART reports, transcripts) fresh on an automatic schedule, instead of manual runs.
- Define a clear **freshness/TTL policy** per data type and a **universe** to pre-warm, so storage and cost stay bounded.

---

## 2. Current State (Code-Grounded)

- Batch ingestion exists but is **manual**:
  - [findata/server/ingestion/sec_10kq_ingest.py](../../findata/server/ingestion/sec_10kq_ingest.py) — batch 10-K/10-Q for a hardcoded `TICKERS` list, run via CLI.
  - [findata/server/ingestion/dart_batch.py](../../findata/server/ingestion/dart_batch.py) — OpenDART modules (accounts/indicators/statements/reports), run via CLI.
- Some freshness logic exists in [company_data.py](../../findata/server/company_data.py): TTL of **10-K/Q = 90 days**, **Form 4 = 7 days**.
- ❌ No scheduler driving these; no universe definition (tickers are hardcoded sample lists); no per-type TTL config in one place.

---

## 3. Design

### 3.1 Universe Definition (don't backfill "everything")

Pre-warming all of EDGAR/DART is huge and mostly unused. Define a **universe** to eagerly maintain; everything else stays lazy ([05](05_lazy_fetch_and_historical_backfill.md)).

- Example universe: S&P 500 + major KOSPI/KOSDAQ names.
- Store the universe in config (`findata/server/ingestion/universe.py` or a JSON), not hardcoded in each script.

### 3.2 Freshness / Refresh Cadence by Data Type

| Data type | Nature | Recommended cadence |
|---|---|---|
| Form 4 (insider) | Irregular, near-realtime | 10-min poll ([04](04_form4_realtime_polling.md)) |
| 10-K / 10-Q (SEC) | Quarterly, immutable once filed | **Daily** RSS check (catches new filings during earnings season). "Quarterly" is too sparse and misses filing dates |
| DART reports (KR) | Quarterly/annual | Daily or weekly check during reporting season |
| Earnings transcripts | Per earnings event | On-demand (lazy) + scheduled sweep of universe after earnings |
| Historical (any) | Immutable | Lazy fetch, cache permanently ([05](05_lazy_fetch_and_historical_backfill.md)) |

> Key correction: "refresh financials once a quarter" is **too infrequent** — you'd miss the day a new report drops. A cheap **daily** RSS/index check is the right granularity; it only *processes* new filings (dedup), so cost stays low.

### 3.3 Centralize TTL

- Move scattered TTLs into one config (`findata/server/ingestion/freshness.py`): `{ "10kq": 90d, "form4": 7d, "dart": ..., "transcript": ... }`, consumed by both `company_data.py` and the schedulers.

### 3.4 Scheduling Mechanism

Same options as [04 §3.3](04_form4_realtime_polling.md): EventBridge+Lambda / ECS scheduled task / in-process APScheduler. Use the **same worker** that runs the Form 4 poller, with multiple jobs at different cadences.

---

## 4. Implementation Steps

1. [ ] **Universe config**: `findata/server/ingestion/universe.py` (load from JSON), replace hardcoded `TICKERS`/`WATCHLIST` references in ingestion scripts with it.
2. [ ] **Freshness config**: `findata/server/ingestion/freshness.py` (per-type TTL); refactor [company_data.py](../../findata/server/company_data.py) to read from it.
3. [ ] **Schedulable entrypoints**: wrap existing batch logic into callables:
   - `run_10kq_refresh(universe)` around [sec_10kq_ingest.py](../../findata/server/ingestion/sec_10kq_ingest.py)
   - `run_dart_refresh(universe, modules)` around [dart_batch.py](../../findata/server/ingestion/dart_batch.py)
   - **Throttle DART** to stay under OpenDART's daily request quota: a configurable per-request delay/rate, exponential backoff when a quota error is returned, and spread large universe runs across the day (chunk the universe rather than firing everything at once).
4. [ ] **Register schedules**: daily 10-K/Q + DART checks on the worker (env-flag gated like the Form 4 poller).
5. [ ] **Freshness-aware serving**: ensure read endpoints consult TTL and trigger refresh when stale (reuse [company_data.py](../../findata/server/company_data.py) cache-status logic).
6. [ ] **Initial universe warm-up**: one-time job to populate the universe on first deploy.

---

## 5. Files to Change/Create

- New: `findata/server/ingestion/universe.py`, `findata/server/ingestion/freshness.py`
- Edit: `findata/server/ingestion/sec_10kq_ingest.py`, `findata/server/ingestion/dart_batch.py` (use universe, expose callables)
- Edit: `findata/server/company_data.py` (read centralized TTL)
- Config: scheduler jobs in deploy ([08](08_deployment_and_infra.md))

---

## 6. Verification

- [ ] Daily 10-K/Q job ingests a newly filed report for a universe ticker within a day of filing.
- [ ] Re-running a job with no new filings inserts nothing (dedup), confirming low cost.
- [ ] A stale cached financial (older than TTL) triggers a refresh on read; a fresh one does not.
- [ ] Universe change (add a ticker) → next run pre-warms it.
- [ ] DART daily/weekly job populates KR data for universe companies.

---

## 7. Pitfalls & Mitigations

Each pitfall is **prevented by a specific step in this plan**.

| Pitfall (what goes wrong) | How this plan prevents it |
|---|---|
| Quarterly-only refresh misses filing dates | §3.2 + Step 4: daily RSS/index checks; dedup keeps cost low |
| Unbounded universe → storage/cost blowup | §3.1 + Step 1: small eager universe, long tail served lazily ([05](05_lazy_fetch_and_historical_backfill.md)) |
| Exceeding OpenDART's daily request cap | Step 3: throttle + backoff on quota errors, spread/chunk large runs |
| TTL duplicated in multiple places drifts | Step 2: centralize TTL in `freshness.py` |
| Schedulers in every instance double-ingest | Step 4 + [08 step 6](08_deployment_and_infra.md): env-flag gate to one worker |
