"""
Database engine / connection factory.

Backend is selected at runtime by ``config.DATABASE_URL``:

  - ``DATABASE_URL`` set   → PostgreSQL (psycopg2).
  - ``DATABASE_URL`` unset → per-file SQLite under ``DATA_DIR`` (the default;
    ideal for a single-box prototype — no separate DB process to run).

Both backends return a connection object with the same small interface
(``execute`` / ``executescript`` / ``executemany`` / ``cursor`` / ``commit`` /
``rollback`` / ``close`` + context manager) that produces dict-like rows.

The SQLite wrapper additionally translates the Postgres SQL the codebase is
written in so individual queries don't need per-backend branches:

  - ``%s`` placeholders          → ``?``
  - ``SERIAL`` column type       → ``INTEGER`` (rowid alias, auto-increments)
  - ``sqlite3`` errors           → the ``psycopg2`` error classes callers catch

``ON CONFLICT ... DO NOTHING`` / ``DO UPDATE ... excluded`` is valid in both
Postgres and modern SQLite (3.24+), so it is left untouched.
"""

from __future__ import annotations

import re
import sqlite3

import psycopg2
import psycopg2.extras

from findata.server.db import config as _config


# Exception classes callers catch as ``psycopg2.Error`` / ``psycopg2.OperationalError``.
# The SQLite wrapper re-raises through these so ``except psycopg2.Error`` blocks
# keep working on either backend.
class OperationalError(psycopg2.OperationalError):
    pass


class Error(psycopg2.Error):
    pass


def get_backend() -> str:
    """Return the active storage backend: 'postgres' or 'sqlite'."""
    return "postgres" if _config.DATABASE_URL else "sqlite"


# ---------------------------------------------------------------------------
# SQLite dialect translation
# ---------------------------------------------------------------------------
_SERIAL_RE = re.compile(r"\bSERIAL\b", re.IGNORECASE)


def _to_sqlite(sql: str) -> str:
    """Adapt a Postgres-flavored statement to SQLite."""
    sql = sql.replace("%s", "?")
    sql = _SERIAL_RE.sub("INTEGER", sql)
    return sql


def _map_err(exc: sqlite3.Error) -> Exception:
    """Map a sqlite3 error onto the psycopg2 error class callers expect."""
    if isinstance(exc, sqlite3.OperationalError):
        return OperationalError(str(exc))
    return Error(str(exc))


class _SqliteCursor:
    """Cursor wrapper that translates SQL and errors on the way through."""

    def __init__(self, cur: sqlite3.Cursor):
        self._cur = cur

    def execute(self, sql, params=()):
        try:
            self._cur.execute(_to_sqlite(sql), params)
        except sqlite3.Error as e:
            raise _map_err(e) from e
        return self

    def executemany(self, sql, seq_of_params):
        try:
            self._cur.executemany(_to_sqlite(sql), seq_of_params)
        except sqlite3.Error as e:
            raise _map_err(e) from e
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur)

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    def close(self):
        self._cur.close()


class _SqliteConn:
    """Connection wrapper matching the psycopg2 ConnWrapper interface."""

    def __init__(self, conn: sqlite3.Connection):
        self._c = conn

    def execute(self, sql, params=()):
        try:
            cur = self._c.execute(_to_sqlite(sql), params)
        except sqlite3.Error as e:
            raise _map_err(e) from e
        return _SqliteCursor(cur)

    def executescript(self, sql):
        try:
            self._c.executescript(_to_sqlite(sql))
        except sqlite3.Error as e:
            raise _map_err(e) from e
        return self

    def executemany(self, sql, seq_of_params):
        cur = self._c.cursor()
        try:
            cur.executemany(_to_sqlite(sql), seq_of_params)
        except sqlite3.Error as e:
            raise _map_err(e) from e
        return _SqliteCursor(cur)

    def cursor(self):
        return _SqliteCursor(self._c.cursor())

    def commit(self):
        self._c.commit()

    def rollback(self):
        self._c.rollback()

    def close(self):
        self._c.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ---------------------------------------------------------------------------
# Postgres wrapper (unchanged behavior)
# ---------------------------------------------------------------------------
class _PgConn:
    """Wrapper to match sqlite3 semantics (execute on conn directly)."""

    def __init__(self, c):
        self._c = c

    def execute(self, sql, params=()):
        cur = self._c.cursor()
        cur.execute(sql, params)
        return cur

    def executescript(self, sql):
        cur = self._c.cursor()
        cur.execute(sql)
        return cur

    def executemany(self, sql, seq_of_params):
        cur = self._c.cursor()
        cur.executemany(sql, seq_of_params)
        return cur

    def commit(self):
        self._c.commit()

    def rollback(self):
        self._c.rollback()

    def cursor(self):
        return self._c.cursor()

    def close(self):
        self._c.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------
def connect(db_path: str | None = None):
    """Open a DB connection through the configured backend.

    Postgres: uses ``DATABASE_URL`` (``db_path`` ignored).
    SQLite:   uses ``db_path`` (one file per logical database).
    Returns a connection producing dict-like rows.
    """
    if get_backend() == "postgres":
        conn = psycopg2.connect(
            _config.DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor
        )
        conn.autocommit = True
        return _PgConn(conn)

    # SQLite
    if db_path is None:
        raise ValueError("db_path is required for the SQLite backend.")
    # timeout= is the busy-wait: concurrent writers wait instead of instantly
    # raising "database is locked".
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row      # dict-like rows: row["col"], dict(row)
    conn.isolation_level = None         # autocommit, matching psycopg2 autocommit=True
    # WAL + NORMAL: readers don't block the writer, and commits don't fsync on
    # every statement (only at checkpoint) — essential for bulk inserts like
    # company_facts (tens of thousands of rows) to finish in seconds, not minutes.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return _SqliteConn(conn)
