"""
Dialect-portable SQL helpers (plan 07 §3.4, Step 1/6).

Keeps the SQLite-vs-Postgres differences in one place so dedup semantics are
preserved across the migration. Today the backend is SQLite, so these emit the
exact SQLite forms (no behavior change); when Postgres is wired they emit the
``ON CONFLICT DO NOTHING`` equivalent.
"""

from __future__ import annotations

from findata.server.db.engine import get_backend


def dedup_insert(insert_into_sql: str, conflict_cols: list[str] | None = None,
                 backend: str | None = None) -> str:
    """Turn an ``INSERT INTO ...`` statement into a deduplicating insert.

    - SQLite  → ``INSERT OR IGNORE INTO ...`` (skips rows that violate a UNIQUE/PK).
    - Postgres → ``INSERT INTO ... ON CONFLICT [(cols)] DO NOTHING``.

    ``cursor.rowcount`` is 1 for an inserted row and 0 for a skipped duplicate
    in both backends, so the existing ``(inserted, skipped)`` accounting holds.

    Args:
        insert_into_sql: A statement beginning with ``INSERT INTO``.
        conflict_cols:   Optional conflict-target columns (Postgres). If omitted,
                         a bare ``ON CONFLICT DO NOTHING`` is used.
    """
    backend = backend or get_backend()
    if backend == "sqlite":
        return insert_into_sql.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)

    # postgres
    body = insert_into_sql.rstrip().rstrip(";")
    target = f" ({', '.join(conflict_cols)})" if conflict_cols else ""
    return f"{body} ON CONFLICT{target} DO NOTHING"


def placeholder(backend: str | None = None) -> str:
    """Return the parameter placeholder for the active backend ('?' or '%s')."""
    backend = backend or get_backend()
    return "%s" if backend == "postgres" else "?"
