"""
Database engine / connection factory (plan 07 §3.2, Step 1).

The single seam through which DB connections are created, so swapping SQLite
for Postgres later is localized here instead of scattered across routers.

Today only SQLite is wired (the MVP backend). When ``DATABASE_URL`` points at
Postgres, ``connect`` raises a clear ``NotImplementedError`` — the Postgres
cut-over (schema, backfill, driver) is intentionally deferred to a later pass
of plan 07. Unset ``DATABASE_URL`` to use SQLite.
"""

from __future__ import annotations

import sqlite3

from findata.server.db import config as _config


def get_backend() -> str:
    """Return the active storage backend: 'sqlite' (default) or 'postgres'."""
    url = _config.DATABASE_URL
    if not url:
        return "sqlite"
    low = url.lower()
    if low.startswith(("postgres://", "postgresql://")):
        return "postgres"
    if low.startswith("sqlite"):
        return "sqlite"
    # Unknown scheme → be safe and treat as SQLite (the only wired backend).
    return "sqlite"


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """Open a DB connection through the configured backend.

    For SQLite, ``db_path`` selects the file (one file per logical DB today),
    the parent directory is created, and ``row_factory`` is set to ``Row`` so
    callers get dict-like rows.

    Raises:
        NotImplementedError: if a Postgres backend is configured (deferred).
        ValueError:          if SQLite is selected but ``db_path`` is missing.
    """
    backend = get_backend()
    if backend == "postgres":
        raise NotImplementedError(
            "Postgres backend is not wired yet (plan 07 cut-over deferred). "
            "Unset DATABASE_URL to use SQLite."
        )

    if db_path is None:
        raise ValueError("db_path is required for the SQLite backend")
    _config.ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
