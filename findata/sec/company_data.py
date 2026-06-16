"""Deprecated company-data orchestration module.

Use ``findata.server.company_data`` instead.
"""

import warnings

warnings.warn(
    "findata.sec.company_data is deprecated; use "
    "findata.server.company_data instead.",
    DeprecationWarning,
    stacklevel=2,
)

from findata.server.company_data import *  # noqa: F401,F403
