"""
Accounts database — user and API key management.

Stores users and their hashed API keys in a SQLite database.
Plaintext keys are shown only once at creation time; only SHA-256
hashes are persisted.
"""

import hashlib
import secrets
from findata.server.db.engine import connect
import psycopg2
import psycopg2.extras
import string
from datetime import datetime, timezone
from typing import Optional

from findata.server.db import config as _config


def _db_path(db_path: str | None) -> str:
    """Resolve db_path, defaulting to the module-level ACCOUNTS_DB."""
    return db_path if db_path is not None else _config.ACCOUNTS_DB


# ── Key generation ──────────────────────────────────────────────────

_BASE62 = string.ascii_letters + string.digits  # a-zA-Z0-9


def _generate_raw_key() -> str:
    """Generate a 32-character base62 random string."""
    return "".join(secrets.choice(_BASE62) for _ in range(32))


def _hash_key(raw_key: str) -> str:
    """Return the hex SHA-256 digest of a raw API key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Schema ──────────────────────────────────────────────────────────

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    email       TEXT    UNIQUE NOT NULL,
    plan        TEXT    NOT NULL DEFAULT 'free',  -- 'owner' | 'free' | 'pro' | ...
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    key_prefix   TEXT    NOT NULL,         -- e.g. 'fd_live_a1b2' (display only)
    key_hash     TEXT    NOT NULL UNIQUE,  -- SHA-256 of the full key
    label        TEXT,                     -- user-assigned name
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL,
    last_used_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
"""


def ensure_accounts_schema(db_path: str | None = None) -> None:
    """Create the users and api_keys tables if they don't exist."""
    path = _db_path(db_path)
    _config.ensure_parent_dir(path)
    conn = connect(path)
    conn.executescript(_SCHEMA_SQL)
    conn.close()


# ── User CRUD ───────────────────────────────────────────────────────

def create_user(
    email: str,
    plan: str = "free",
    *,
    db_path: str | None = None,
) -> int:
    """Insert a new user and return their id.

    If the email already exists, return the existing user's id.
    """
    path = _db_path(db_path)
    ensure_accounts_schema(path)
    conn = connect(path)
    try:
        conn.execute(
            "INSERT INTO users (email, plan, created_at) VALUES (%s, %s, %s) ON CONFLICT (email) DO NOTHING",
            (email, plan, _now_iso()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM users WHERE email = %s", (email,)
        ).fetchone()
        return row[0]
    finally:
        conn.close()


# ── API key CRUD ────────────────────────────────────────────────────

def create_api_key(
    user_id: int,
    label: Optional[str] = None,
    *,
    env: str = "live",
    db_path: str | None = None,
) -> str:
    """Create an API key for a user, store its hash, and return the plaintext.

    The plaintext key is returned **only once**. It is never stored.

    Args:
        user_id: The user's id.
        label:   Optional human-readable label for the key.
        env:     Key environment prefix: 'live' or 'test'.
        db_path: Path to the accounts database.

    Returns:
        The full plaintext key (e.g. ``fd_live_aBcDeFgH...``).
    """
    path = _db_path(db_path)
    ensure_accounts_schema(path)
    raw = _generate_raw_key()
    prefix = f"fd_{env}_"
    full_key = f"{prefix}{raw}"
    key_hash = _hash_key(full_key)
    display_prefix = full_key[:12]  # e.g. 'fd_live_a1b2'

    conn = connect(path)
    try:
        conn.execute(
            """
            INSERT INTO api_keys (user_id, key_prefix, key_hash, label, active, created_at)
            VALUES (%s, %s, %s, %s, 1, %s)
            """,
            (user_id, display_prefix, key_hash, label, _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()

    return full_key


def get_user_by_key(
    raw_key: str,
    *,
    db_path: str | None = None,
) -> Optional[dict]:
    """Look up a user by their raw API key.

    Returns a dict with user + key info, or None if invalid/inactive.
    """
    path = _db_path(db_path)
    key_hash = _hash_key(raw_key)

    conn = connect(path)
    
    try:
        row = conn.execute(
            """
            SELECT
                k.id        AS key_id,
                k.user_id,
                k.key_prefix,
                k.key_hash,
                k.label     AS key_label,
                k.active,
                k.last_used_at,
                u.email,
                u.plan
            FROM api_keys k
            JOIN users u ON u.id = k.user_id
            WHERE k.key_hash = %s
            """,
            (key_hash,),
        ).fetchone()

        if row is None:
            return None

        # Constant-time comparison as defense-in-depth
        if not secrets.compare_digest(key_hash, row["key_hash"]):
            return None

        if not row["active"]:
            return None

        result = dict(row)
        del result["key_hash"]  # Never expose the hash
        return result
    finally:
        conn.close()


def update_last_used(key_id: int, *, db_path: str | None = None) -> None:
    """Update the last_used_at timestamp for a key."""
    path = _db_path(db_path)
    conn = connect(path)
    try:
        conn.execute(
            "UPDATE api_keys SET last_used_at = %s WHERE id = %s",
            (_now_iso(), key_id),
        )
        conn.commit()
    finally:
        conn.close()


def deactivate_key(key_id: int, *, db_path: str | None = None) -> None:
    """Deactivate an API key (soft-delete)."""
    path = _db_path(db_path)
    conn = connect(path)
    try:
        conn.execute(
            "UPDATE api_keys SET active = 0 WHERE id = %s",
            (key_id,),
        )
        conn.commit()
    finally:
        conn.close()


def list_keys_for_user(
    user_id: int, *, db_path: str | None = None
) -> list[dict]:
    """Return all API keys (metadata only) for a user."""
    path = _db_path(db_path)
    conn = connect(path)
    
    try:
        rows = conn.execute(
            """
            SELECT id, key_prefix, label, active, created_at, last_used_at
            FROM api_keys
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]

