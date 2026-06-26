"""
Database engine / connection factory (PostgreSQL).

Swapped from SQLite to PostgreSQL via psycopg2.
"""

from __future__ import annotations

import os
import psycopg2
import psycopg2.extras

from findata.server.db import config as _config

# Add custom exception mappings to match what the codebase expects
class OperationalError(psycopg2.OperationalError):
    pass
class Error(psycopg2.Error):
    pass

def get_backend() -> str:
    """Return the active storage backend."""
    return "postgres"

def connect(db_path: str | None = None):
    """Open a DB connection through the configured backend.
    
    Ignores db_path since Postgres uses DATABASE_URL.
    Returns a connection that produces dict-like rows.
    """
    url = _config.DATABASE_URL
    if not url:
        raise ValueError("DATABASE_URL is not set. Required for PostgreSQL backend.")
        
    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.DictCursor)
    conn.autocommit = True
    
    # Simple wrapper to match sqlite3 semantics (execute on conn directly)
    class ConnWrapper:
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
            
    return ConnWrapper(conn)
