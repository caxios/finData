# 05 — Lazy Fetch & Historical Backfill

> **Phase 2 / Order 5**
> **Prerequisite**: None (extends existing behavior)
> **Related**: [04_form4_realtime_polling.md](04_form4_realtime_polling.md), [06_scheduled_ingestion_and_freshness.md](06_scheduled_ingestion_and_freshness.md)

---

## 1. Goal

- Keep the existing **cache-aside** behavior: on a cache miss, fetch from EDGAR, store, then serve — so the next user gets it from storage.
- Add the currently **missing** capability: fetch a **specific historical period** (e.g. "MRVL 2019 insider trades"), not just "recent N filings."

---

## 2. Current State (Code-Grounded)

### What already works ✅
`GET /api/trades?ticker=MRVL` (`auto_refresh=True` default) in [findata/server/api/api_form4.py](../../findata/server/api/api_form4.py):

```
1. _tickers_missing_from_db("MRVL") → is MRVL in the DB?
2. if missing → parse_form4_for_ticker("MRVL", count=N) → save_to_db
3. read from DB and serve
4. next caller for MRVL → step 1 finds rows → no fetch, serves cached
```

- `parse_form4_for_ticker(ticker, count)` resolves ticker→CIK and pulls recent filings via the `getcompany` Atom feed ([sec_form4_watchlist.py:25,68](../../findata/sec/utils/form4/sec_form4_watchlist.py)). Works for **any** ticker, not just `WATCHLIST`.

### What's missing ❌
- `parse_form4_for_ticker` is **"recent N" only** (`count`). EDGAR's `getcompany` `count` maxes at 100; the API handler caps it lower (`Query(ge=1, le=40)` in [api_form4.py](../../findata/server/api/api_form4.py)).
- **No date-range fetch.** `/api/trades` `date_from`/`date_to` only **filter rows already in the DB** — they do not control what gets fetched. So requesting `date_from=2019` for a never-fetched ticker returns empty/partial.
- **Cache-miss semantics are coarse**: presence is "any rows exist for ticker," not "rows covering the requested period exist." A ticker fetched for recent data looks "present" even when 2019 is absent.

---

## 3. Design

### 3.1 Two fetch modes for a ticker

| Mode | Source | Use |
|---|---|---|
| **Recent N** (exists) | `getcompany` Atom feed, `count` | "latest insider activity for X" |
| **Historical period** (new) | EDGAR **submissions JSON** `https://data.sec.gov/submissions/CIK##########.json` | "X's filings in 2019" |

Submissions JSON lists **all** filings for a company (form type, accession, filing date). Filter to Form 4 + the requested date window, then fetch+parse only those documents. This is the right primitive for arbitrary historical ranges.

### 3.2 Period-aware cache-miss check

Replace "does the ticker have any rows?" with "does the DB cover the requested `[date_from, date_to]`?":

- Track per-ticker **coverage** (e.g. a `coverage` table: `ticker, covered_from, covered_to` or a set of fetched periods).
- On request with a date range:
  - If coverage includes the range → serve from DB.
  - Else → backfill the missing window via submissions JSON, record coverage, then serve.

### 3.3 Lazy-fetch + billing/rate-limit interaction

- A cache-miss request triggers an upstream EDGAR call → it is a **higher-credit event** ([02 §3.1](02_metering_and_rate_limiting.md)).
- Protect upstream with the rate limiter and **single-flight**: if 10 users request the same uncached ticker/period simultaneously, fetch once, not ten times (per-key lock on `(ticker, period)`).

---

## 4. Implementation Steps

1. [ ] **Historical fetcher**: `findata/sec/utils/form4/form4_submissions.py` with `fetch_form4_by_period(ticker, date_from, date_to)`:
   - resolve ticker→CIK ([_cik.py](../../findata/sec/_cik.py)), GET submissions JSON, filter `form == '4'/'4/A'` and filing date in window, fetch+parse each via existing `parse_form4` ([form4_parser.py](../../findata/sec/utils/form4/form4_parser.py)), return `save_to_db`-shaped dicts. Handle the `submissions` pagination (`files[].name` older shards) for deep history.
2. [ ] **Coverage tracking**: add a `form4_coverage` table + helpers in [form4_db.py](../../findata/server/db/form4_db.py) (`get_coverage(ticker)`, `record_coverage(ticker, from, to)`).
3. [ ] **Period-aware `_lazy_load`**: in [api_form4.py](../../findata/server/api/api_form4.py), when `date_from`/`date_to` are present, check coverage and call `fetch_form4_by_period` for the missing window instead of `parse_form4_for_ticker`. If the ticker can't be resolved to a CIK, return **422 (invalid ticker)** with a clear message rather than a silent empty list; if it resolves but has no Form 4 filings in the window, return an empty result with `200` (valid, just nothing there).
4. [ ] **Single-flight guard**: per-`(ticker, period)` lock around the fetch (in-process lock for MVP; distributed lock if multi-instance).
5. [ ] **Raise the count cap (optional)**: change `Query(ge=1, le=40)` → `le=100` for the recent-N path if desired.
6. [ ] **Credit weight**: register the lazy/backfill path as a higher-credit endpoint in [costs.py](02_metering_and_rate_limiting.md).

---

## 5. Files to Change/Create

- New: `findata/sec/utils/form4/form4_submissions.py`
- Edit: `findata/server/db/form4_db.py` (coverage table + helpers)
- Edit: `findata/server/api/api_form4.py` (`_lazy_load` period-aware, single-flight, count cap)
- Related: credit weights in `findata/server/billing/costs.py` ([02](02_metering_and_rate_limiting.md))

---

## 6. Verification

- [ ] `GET /api/trades?ticker=MRVL` (no date) → recent filings fetched + stored, second call served from cache (existing behavior preserved).
- [ ] `GET /api/trades?ticker=MRVL&date_from=2019-01-01&date_to=2019-12-31` on a never-fetched window → backfills 2019 from submissions JSON, returns 2019 rows.
- [ ] Repeat the 2019 request → served from DB, no new upstream fetch (coverage recorded).
- [ ] Requesting a different uncovered year fetches only that window.
- [ ] Concurrent identical uncached requests trigger exactly one upstream fetch (single-flight).

---

## 7. Pitfalls & Mitigations

Each pitfall is **prevented by a specific step in this plan**.

| Pitfall (what goes wrong) | How this plan prevents it |
|---|---|
| `date_from`/`date_to` filter instead of fetching (the core bug) | Step 3: make `_lazy_load` period-aware so a date range triggers a backfill |
| "Ticker present" ≠ "period present" → incomplete history served | Step 2: coverage tracking records which windows are cached and refetches the missing ones |
| Submissions JSON pagination truncates deep history | Step 1: handle older shards listed under `filings.files[]` |
| Thundering herd / SEC rate limit on popular uncached tickers | Step 4 single-flight + the rate limiter ([02 §3.5](02_metering_and_rate_limiting.md)) |
| CIK resolution failure returns a silent empty list | Step 3: return **422 (invalid ticker)** instead of empty |
| Wrong/empty User-Agent on fan-out fetches | Step 1 reuses `parse_form4`'s `HEADERS`; keep the real SEC User-Agent ([04 step 5](04_form4_realtime_polling.md)) |
