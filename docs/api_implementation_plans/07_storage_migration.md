# 07 — Storage Migration (SQLite → Postgres + S3)

> **Phase 3 / Order 7**
> **Prerequisite**: Phases 1–2 working on SQLite
> **Related**: [08_deployment_and_infra.md](08_deployment_and_infra.md)

---

## 1. Goal

- Move from single-file SQLite to a storage layer that handles **multi-user concurrent reads/writes** and scales: **Postgres (RDS)** for structured data, **S3** for raw filing documents.
- Do it **only when traffic justifies it** — SQLite is fine for the MVP.

---

## 2. Current State (Code-Grounded)

- All persistence is SQLite under `~/.findata/sec_db/` ([findata/server/db/config.py](../../findata/server/db/config.py)):
  - `insider_watchlist.db`, `insider_all.db`, `sec_10kq.db`, `company_facts.db`, `earnings_transcripts.db` (+ `accounts.db` from [01](01_auth_and_api_keys.md)).
- DB access is raw `sqlite3` with `conn.row_factory = sqlite3.Row` and hand-written SQL ([api_form4.py](../../findata/server/api/api_form4.py), `db/*.py`).
- Writers: lazy fetch ([05](05_lazy_fetch_and_historical_backfill.md)), the Form 4 poller ([04](04_form4_realtime_polling.md)), scheduled ingestion ([06](06_scheduled_ingestion_and_freshness.md)). Readers: all API endpoints.
- ⚠️ **Concurrency risk**: SQLite serializes writes and locks the file; a busy poller + many readers + lazy-fetch writes will contend (`database is locked`).

---

## 3. Design

### 3.1 What goes where

| Data | Target | Why |
|---|---|---|
| Structured rows (trades, facts, filings metadata, users, usage) | **Postgres (RDS)** | Concurrent writes, indexes, transactions, analytics |
| Raw filing documents (Form 4 XML, 10-K/Q HTML/text, PDFs) | **S3** | Cheap, large blobs; DB stores the S3 key/pointer |

- Endpoints that currently parse-on-read (e.g. `/api/download-pdf` via Playwright in [api_10kq.py](../../findata/server/api/api_10kq.py)) write artifacts to S3 and serve via pointer/signed URL.

### 3.2 Access-layer abstraction (do this first, even on SQLite)

The current code embeds SQL inline. Before migrating, introduce a thin **repository/DAO layer** so the engine swap is localized:

- `findata/server/db/engine.py` — connection factory (SQLite **or** Postgres via env `DATABASE_URL`).
- Repositories (`form4_repo.py`, `facts_repo.py`, ...) expose methods (`insert_trades`, `query_trades`, ...) instead of raw SQL in routers.
- Consider SQLAlchemy Core (not necessarily full ORM) for dialect portability, or keep hand-written SQL with a dialect switch.

### 3.3 Migration approach

1. Stand up Postgres (RDS).
2. Create schema (translate `CREATE TABLE`s; SQLite `INTEGER PRIMARY KEY` → `BIGSERIAL`/`IDENTITY`, watch `AUTOINCREMENT`, types, `UPSERT`/`ON CONFLICT` for dedup).
3. Backfill: export SQLite → load into Postgres (one-off script per table).
4. Flip `DATABASE_URL`, run in parallel/read-verify, then cut over.

### 3.4 Preserve dedup semantics

- `save_to_db`'s `(inserted, skipped)` dedup ([form4_db.py](../../findata/server/db/form4_db.py)) must map to Postgres `INSERT ... ON CONFLICT (accession/unique_key) DO NOTHING`. Keep the same unique keys used today (e.g. `(source_url, owner_name, transaction_date, amount)` referenced in [api_form4.py](../../findata/server/api/api_form4.py) rankings dedup).

---

## 4. Implementation Steps

1. [ ] **Introduce DAO layer** (on SQLite first): `engine.py` + per-domain repositories; move inline SQL out of routers. Ship + verify with no behavior change.
2. [ ] **Add `DATABASE_URL`** config; SQLite remains default.
3. [ ] **Postgres schema** scripts (mirror current tables + uniques + indexes).
4. [ ] **Backfill scripts**: SQLite → Postgres per table.
5. [ ] **S3 for blobs**: `findata/server/storage/s3.py` (put/get/signed URL); store keys in DB; update PDF/raw-doc paths.
6. [ ] **Switch dedup to UPSERT** in repositories.
7. [ ] **Cut over**: point `DATABASE_URL` at RDS; verify counts match; decommission SQLite.
8. [ ] **Move rate-limit/usage state** that needs sharing across instances to Postgres/Redis ([02](02_metering_and_rate_limiting.md), [08](08_deployment_and_infra.md)).

---

## 5. Files to Change/Create

- New: `findata/server/db/engine.py`, `findata/server/db/*_repo.py`, `findata/server/storage/s3.py`, `migrations/` (schema + backfill)
- Edit: `findata/server/db/config.py` (`DATABASE_URL`), all `db/*.py` (route through repos), routers (use repos, not raw `sqlite3`), [api_10kq.py](../../findata/server/api/api_10kq.py) (PDF/raw → S3)

---

## 6. Verification

- [ ] DAO refactor on SQLite: full endpoint suite behaves identically (no regression).
- [ ] Row counts per table match after SQLite→Postgres backfill.
- [ ] Concurrent poller writes + many API reads: no lock errors on Postgres (repro the SQLite contention first to confirm the motivation).
- [ ] Dedup: re-ingesting the same filings inserts 0 rows via `ON CONFLICT`.
- [ ] Raw docs/PDFs round-trip through S3 and serve via pointer/signed URL.

---

## 7. Pitfalls & Mitigations

Each pitfall is **prevented by a specific step in this plan**.

| Pitfall (what goes wrong) | How this plan prevents it |
|---|---|
| Migrating prematurely | §1 + step order: stay on SQLite for the MVP; migrate only on lock contention / multi-instance need |
| SQL dialect gaps (`AUTOINCREMENT`, booleans, `INSERT OR IGNORE` vs `ON CONFLICT`) break queries | Step 1: introduce the DAO layer first so dialect differences live in one place |
| Changing unique keys silently breaks dedup | §3.4 + Step 6: keep the exact unique keys, map to `ON CONFLICT DO NOTHING` |
| Storing large blobs in the DB | §3.1 + Step 5: raw text/PDF go to S3, DB stores only the key |
| Multi-instance state stuck in-process (rate-limit buckets, single-flight locks) | Step 8: externalize to Redis/Postgres |
