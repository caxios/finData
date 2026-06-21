"""
Data universe configuration (plan 06 §3.1).

The *universe* is the bounded set of companies we eagerly pre-warm and keep
fresh on a schedule. Everything outside it is served lazily on demand
(plan 05), which keeps storage and cost bounded.

The universe is stored as JSON (``universe.json`` next to this file) so it can
be edited without touching code, and overridden per-deployment with the
``FINDATA_UNIVERSE_FILE`` environment variable.

Shape::

    { "us": ["AAPL", ...],   # SEC tickers
      "kr": ["삼성전자", ...] }  # OpenDART company names
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULT_FILE = Path(__file__).parent / "universe.json"


def _universe_path(path: str | None = None) -> str:
    if path is not None:
        return path
    return os.getenv("FINDATA_UNIVERSE_FILE", str(_DEFAULT_FILE))


def load_universe(path: str | None = None) -> dict:
    """Load the universe JSON. Returns {} if the file is missing/invalid."""
    p = _universe_path(path)
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def get_us_universe(path: str | None = None) -> list[str]:
    """US SEC tickers in the universe (upper-cased, de-duplicated, ordered)."""
    raw = load_universe(path).get("us", []) or []
    seen: set[str] = set()
    out: list[str] = []
    for t in raw:
        u = str(t).strip().upper()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def get_kr_universe(path: str | None = None) -> list[str]:
    """OpenDART company names in the universe (de-duplicated, ordered)."""
    raw = load_universe(path).get("kr", []) or []
    seen: set[str] = set()
    out: list[str] = []
    for n in raw:
        name = str(n).strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out
