"""
findata core configuration — library layer.

Defines the base DATA_DIR path only. No directories are created on import.
Database paths and directory creation are handled by the server layer
(``findata.server.db.config``).
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Default data directory is ~/.findata unless overridden by FINDATA_DATA_DIR
_home_dir = Path.home()
DATA_DIR = Path(os.getenv("FINDATA_DATA_DIR", _home_dir / ".findata"))
