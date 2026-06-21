"""
Server-specific database path configuration.

This module defines all SQLite database paths used by the server layer
without creating directories on import. Server code should call
``ensure_data_dirs()`` during startup or ``ensure_parent_dir()`` before
opening a SQLite file.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# Base data directory — defaults to ~/.findata unless overridden
_home_dir = Path.home()
DATA_DIR = Path(os.getenv("FINDATA_DATA_DIR", _home_dir / ".findata"))

# ── SEC database directory ──────────────────────────────────────────
SEC_DB_DIR = DATA_DIR / "sec_db"

# ── DART cache directory ────────────────────────────────────────────
DART_CACHE_DIR = DATA_DIR / "dart_cache"

# ── General data directory ──────────────────────────────────────────
GENERAL_DATA_DIR = DATA_DIR / "data"

# ── Individual DB file paths ────────────────────────────────────────
INSIDER_WATCHLIST_DB = str(SEC_DB_DIR / "insider_watchlist.db")
INSIDER_ALL_DB = str(SEC_DB_DIR / "insider_all.db")
SEC_10KQ_DB = str(SEC_DB_DIR / "sec_10kq.db")
COMPANY_FACTS_DB = str(SEC_DB_DIR / "company_facts.db")
EARNINGS_DB = str(SEC_DB_DIR / "earnings_transcripts.db")
ACCOUNTS_DB = str(SEC_DB_DIR / "accounts.db")


def ensure_data_dirs() -> None:
    """Create all server-managed data directories."""
    SEC_DB_DIR.mkdir(parents=True, exist_ok=True)
    DART_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    GENERAL_DATA_DIR.mkdir(parents=True, exist_ok=True)


def ensure_parent_dir(path: str | os.PathLike) -> None:
    """Create the parent directory for a server-managed file path."""
    Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
