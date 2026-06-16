"""Deprecated 10-K/10-Q API router module.

Use ``findata.server.api.api_10kq`` instead.
"""

import warnings

warnings.warn(
    "findata.sec.api.api_10kq is deprecated; use "
    "findata.server.api.api_10kq instead.",
    DeprecationWarning,
    stacklevel=2,
)

from findata.server.api.api_10kq import *  # noqa: F401,F403
