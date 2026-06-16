"""Deprecated company-facts SQLite helpers.

Use ``findata.server.db.company_facts_db`` instead.
"""

import warnings

warnings.warn(
    "findata.sec.company_facts.company_facts_db is deprecated; use "
    "findata.server.db.company_facts_db instead.",
    DeprecationWarning,
    stacklevel=2,
)

from findata.server.db.company_facts_db import *  # noqa: F401,F403
