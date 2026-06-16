"""Deprecated CIO chat API router module.

Use ``findata.server.api.api_cio_chat`` instead.
"""

import warnings

warnings.warn(
    "findata.sec.api.api_cio_chat is deprecated; use "
    "findata.server.api.api_cio_chat instead.",
    DeprecationWarning,
    stacklevel=2,
)

from findata.server.api.api_cio_chat import *  # noqa: F401,F403
