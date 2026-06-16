"""Deprecated earnings-call API router module.

Use ``findata.server.api.api_earnigscall`` instead.
"""

import warnings

warnings.warn(
    "findata.sec.api.api_earnigscall is deprecated; use "
    "findata.server.api.api_earnigscall instead.",
    DeprecationWarning,
    stacklevel=2,
)

from findata.server.api.api_earnigscall import *  # noqa: F401,F403
