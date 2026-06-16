"""Deprecated additional SEC filing SQLite helpers.

Use ``findata.server.db.sec_filings_db`` instead.
"""

import warnings

warnings.warn(
    "findata.sec.utils.sec_filings.db is deprecated; use "
    "findata.server.db.sec_filings_db instead.",
    DeprecationWarning,
    stacklevel=2,
)

from findata.server.db.sec_filings_db import *  # noqa: F401,F403
