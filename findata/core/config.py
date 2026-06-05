import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Default data directory is ~/.findata unless overridden by FINDATA_DATA_DIR
_home_dir = Path.home()
DATA_DIR = Path(os.getenv("FINDATA_DATA_DIR", _home_dir / ".findata"))

# Ensure base data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Define subdirectories
SEC_DB_DIR = DATA_DIR / "sec_db"
SEC_DB_DIR.mkdir(parents=True, exist_ok=True)

DART_CACHE_DIR = DATA_DIR / "dart_cache"
DART_CACHE_DIR.mkdir(parents=True, exist_ok=True)

GENERAL_DATA_DIR = DATA_DIR / "data"
GENERAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
