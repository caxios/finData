"""Deprecated earnings transcript SQLite helpers.

Use ``findata.server.db.earnings_db`` instead.
"""

import warnings

warnings.warn(
    "findata.sec.utils.earnings_call.earnings_transcripts_db is deprecated; "
    "use findata.server.db.earnings_db instead.",
    DeprecationWarning,
    stacklevel=2,
)

from findata.server.db.earnings_db import *  # noqa: F401,F403
