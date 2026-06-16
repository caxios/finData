"""Deprecated Form 4 API router module.

Use ``findata.server.api.api_form4`` instead.
"""

import warnings

warnings.warn(
    "findata.sec.api.api_form4 is deprecated; use "
    "findata.server.api.api_form4 instead.",
    DeprecationWarning,
    stacklevel=2,
)

from findata.server.api.api_form4 import *  # noqa: F401,F403
