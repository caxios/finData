"""
Server-specific database path configuration.

This module defines all SQLite database paths used by the server layer
and creates the necessary directories. Only imported by server code —
the library layer never touches these paths.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base data directory — defaults to ~/.findata unless overridden
_home_dir = Path.home()
DATA_DIR = Path(os.getenv("FINDATA_DATA_DIR", _home_dir / ".findata"))

# ── SEC database directory ──────────────────────────────────────────
SEC_DB_DIR = DATA_DIR / "sec_db"
SEC_DB_DIR.mkdir(parents=True, exist_ok=True)

# ── DART cache directory ────────────────────────────────────────────
DART_CACHE_DIR = DATA_DIR / "dart_cache"
DART_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── General data directory ──────────────────────────────────────────
GENERAL_DATA_DIR = DATA_DIR / "data"
GENERAL_DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Individual DB file paths ────────────────────────────────────────
INSIDER_WATCHLIST_DB = str(SEC_DB_DIR / "insider_watchlist.db")
INSIDER_ALL_DB = str(SEC_DB_DIR / "insider_all.db")
SEC_10KQ_DB = str(SEC_DB_DIR / "sec_10kq.db")
COMPANY_FACTS_DB = str(SEC_DB_DIR / "company_facts.db")
EARNINGS_DB = str(SEC_DB_DIR / "earnings_transcripts.db")
