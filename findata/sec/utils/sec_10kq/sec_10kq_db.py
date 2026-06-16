"""Deprecated 10-K/10-Q SQLite helpers.

Use ``findata.server.db.sec_10kq_db`` instead.
"""

import warnings

warnings.warn(
    "findata.sec.utils.sec_10kq.sec_10kq_db is deprecated; use "
    "findata.server.db.sec_10kq_db instead.",
    DeprecationWarning,
    stacklevel=2,
)

from findata.server.db.sec_10kq_db import *  # noqa: F401,F403
