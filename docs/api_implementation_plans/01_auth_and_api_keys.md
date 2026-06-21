# 01 — Authentication & Client API Keys

> **Phase 1 / Order 1**
> **Prerequisite**: None (implement first)
> **Related**: [02_metering_and_rate_limiting.md](02_metering_and_rate_limiting.md), [03_billing_and_pricing.md](03_billing_and_pricing.md)

---

## 1. Goal

- Be able to **identify the user** calling the API (issue/validate client API keys).
- Let **me (developer) use it without billing**, while **other users are identified by key** and become subject to metering/billing.
- Close the current unauthenticated, fully-open state.

---

## 2. Current State (Code-Grounded)

- [findata/server/app.py](../../findata/server/app.py): **No** auth middleware, `CORSMiddleware(allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])`.
  - → **Deploying now lets anyone call free & unlimited.** First thing to lock down for commercialization.
- All routers (`api_form4`, `api_10kq`, `api_earnigscall`, `api_cio_chat`) are registered with no auth dependency.
- Upstream keys (`OPEN_DART_API`, `GOOGLE_API_KEY`, `TAVILY_API_KEY`) are loaded from env vars — these are (A) upstream keys, left as-is. What we build is (B) client keys.

---

## 3. Design

### 3.1 Self-exemption Strategy — Most Important

Make **network path separation** the #1 approach, no code branching.

| Approach | Description | Recommendation |
|---|---|---|
| **A. Path separation (recommended)** | Don't expose the Origin server directly. Regular users reach it only via the gateway. I connect to Origin directly via VPN/SSH tunnel/internal network/localhost → physically never touch the billing layer | ★★★ |
| **B. owner key flag** | When the gateway is the single entry point, mark my key as `plan=owner` (unlimited, $0) | ★★ (can combine with A) |

> Conclusion: Make **A the default**, and use B as a fallback only when a single entry point is enforced. Either way, never build business logic like `if user == me`.

### 3.2 API Key Data Model

In a new DB (or, before [07 migration](07_storage_migration.md), a new SQLite file `~/.findata/sec_db/accounts.db`):

```sql
-- Users (billing subjects)
CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    plan          TEXT NOT NULL DEFAULT 'free',   -- 'owner' | 'free' | 'pro' | ...
    created_at    TEXT NOT NULL
);

-- API keys (store only a hash, never the plaintext)
CREATE TABLE api_keys (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    key_prefix    TEXT NOT NULL,        -- e.g. 'fd_live_a1b2' (display/identify only)
    key_hash      TEXT NOT NULL UNIQUE, -- SHA-256 of the full key
    label         TEXT,                 -- user-assigned name
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    last_used_at  TEXT
);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
```

### 3.3 Key Format & Issuance

- Format: `fd_live_<32-byte base62 random>` (use `fd_test_*` for test keys).
- On issuance: show the plaintext key to the user **only once, right after creation**; store only `key_hash = sha256(key)` in the DB.
- On validation: hash the request key → look up `api_keys.key_hash` → check `active=1` → load `user`/`plan`.
- **Constant-time comparison**: validate by the indexed `key_hash` lookup, and where you compare strings use `secrets.compare_digest` (never `==` on the raw key). Combined with the 32-byte entropy of the key, this makes guessing/timing attacks infeasible.

### 3.4 Validation Flow (FastAPI Depends)

```
Request ─▶ Authorization: Bearer <key>  or  X-API-Key: <key>
        ─▶ require_api_key dependency:
             1) Extract key from header (401 if missing)
             2) sha256 → look up api_keys (401 if not found or inactive)
             3) Load users → inject into request.state.user
             4) Update last_used_at (async/batched)
        ─▶ Run route handler
```

- Attach `dependencies=[Depends(require_api_key)]` to all data routers.
- Exempt public endpoints like `/health`, `/docs`.

---

## 4. Implementation Steps

1. [ ] **New accounts DB module**: `findata/server/db/accounts_db.py`
   - `ensure_accounts_schema()`, `create_user(email, plan)`, `create_api_key(user_id, label)` (returns plaintext + stores hash), `get_user_by_key(raw_key)`, `deactivate_key(key_id)`.
   - Add `ACCOUNTS_DB` path to [config.py](../../findata/server/db/config.py).
2. [ ] **New auth dependency**: `findata/server/auth.py`
   - `require_api_key(request)` FastAPI dependency. Parse header → validate → inject `request.state.user`.
   - Also `optional_api_key` for public+identified hybrid endpoints.
3. [ ] **Apply to routers**: Add `dependencies=[Depends(require_api_key)]` to each `api_*.py`'s `APIRouter(...)`, or apply uniformly at router registration in `app.py`.
4. [ ] **Tighten CORS**: Restrict `allow_origins=["*"]` in [app.py](../../findata/server/app.py) to an explicit allowlist of your frontend/console domains. (For a server-to-server API, CORS matters less, but specify it if there's a browser console.)
5. [ ] **Admin key-issuing CLI/script**: `python -m findata.server.tools.issue_key --email me@x.com --plan owner`. For issuing my owner key and test user keys.
6. [ ] **Seed owner key**: Create my account with `plan='owner'` (the 3.1-B fallback).

> **Cross-cutting from [09](09_launch_readiness.md) — do these *now*, while you're in `app.py`/routers:**
> - **API versioning (09 §3.3)**: mount routers under `/v1/` from the start. Adding it later breaks integrated clients.
> - **Unified error contract (09 §3.4)**: register the central exception handler now so every endpoint (including 401) returns the same error shape.
> - **Signup path decision (09 §3.1)**: decide managed-gateway vs direct before building more, since it determines how much of this `users`/`api_keys` model you build yourself vs delegate.

---

## 5. Files to Change/Create

- New: `findata/server/db/accounts_db.py`
- New: `findata/server/auth.py`
- New: `findata/server/tools/issue_key.py`
- Edit: `findata/server/db/config.py` (`ACCOUNTS_DB` path + include in `ensure_data_dirs`)
- Edit: `findata/server/app.py` (apply auth dependency, narrow CORS)
- Edit: each `findata/server/api/api_*.py` (router dependency)

---

## 6. Verification

- [ ] Call `/api/trades` with no key → **401**.
- [ ] Call with a valid key → **200**, correct data.
- [ ] Call with a deactivated key → **401**.
- [ ] Call with the owner key → OK (quota exemption verified later in [02](02_metering_and_rate_limiting.md)).
- [ ] Confirm `last_used_at` updates.
- [ ] Confirm plaintext keys are not stored (hash only) in the DB.

---

## 7. Pitfalls & Mitigations

Each pitfall below is a **failure mode that a specific step in this plan prevents** — not an open problem you still have to solve elsewhere.

| Pitfall (what goes wrong) | How this plan prevents it |
|---|---|
| Storing plaintext keys → a DB leak exposes every user's key | §3.3 + Step 1: store only `key_hash = sha256(key)`; plaintext is shown once and never persisted |
| Timing/guessing attacks on key comparison | §3.3 + Step 2: validate via indexed `key_hash` lookup and `secrets.compare_digest`; 32-byte random keys make guessing infeasible |
| Leaked owner key drains all free usage | Step 4–6 + [08 §3.4](08_deployment_and_infra.md): owner uses the private network path (self-exemption A), so the key alone isn't the only guard |
| An endpoint left unauthenticated by accident | Step 3: attach `require_api_key` **uniformly at router registration**, not per-route |
| Metering/billing can't identify the caller | Step 2: `require_api_key` reliably injects `request.state.user`, which [02](02_metering_and_rate_limiting.md) consumes |
