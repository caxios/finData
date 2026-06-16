"""Deprecated Form 4 SQLite helpers.

Use ``findata.server.db.form4_db`` instead.
"""

import warnings

warnings.warn(
    "findata.sec.utils.form4.form4_db is deprecated; use "
    "findata.server.db.form4_db instead.",
    DeprecationWarning,
    stacklevel=2,
)

from findata.server.db.form4_db import *  # noqa: F401,F403
