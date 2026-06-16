"""Deprecated FastAPI entrypoint.

Use ``findata.server.app`` instead.
"""

import warnings

warnings.warn(
    "findata.sec.app is deprecated; use findata.server.app instead.",
    DeprecationWarning,
    stacklevel=2,
)

from findata.server.app import app

__all__ = ["app"]
