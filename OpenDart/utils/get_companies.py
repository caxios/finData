"""
get_companies.py – Fetch and cache all publicly traded Korean corporate codes.

Uses the dart-fss library to download the full DART corporate list, filters
for listed companies (those with a valid stock_code), and stores the result
in a local JSON cache so the API is only called once.

Usage from another script:
    from get_companies import COMPANY_CODES

    code = COMPANY_CODES.get("삼성전자")
    if code:
        print(f"Corp code for 삼성전자: {code}")
"""

import json
import os
from pathlib import Path

import dart_fss as df
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_CACHE_FILE = Path(__file__).resolve().parent.parent / "auto_corp_cache.json"


def _load_company_codes() -> dict[str, str]:
    """Return {company_name: corp_code} for all publicly traded companies.

    Caching logic:
      1. If auto_corp_cache.json exists  → load and return it (no API call).
      2. Otherwise                       → call DART API, filter listed
         companies, save the cache, then return the dict.
    """

    # --- Cache hit: return immediately ---
    if _CACHE_FILE.exists():
        with _CACHE_FILE.open(encoding="utf-8") as f:
            return json.load(f)

    # --- Cache miss: fetch from DART API ---
    load_dotenv()
    api_key = os.getenv("OPEN_DART_API")
    if not api_key:
        raise ValueError(
            "OPEN_DART_API key not found. "
            "Set it in the .env file or as an environment variable."
        )

    df.set_api_key(api_key=api_key)
    corp_list = df.get_corp_list()

    # Keep only listed companies (non-empty stock_code)
    company_codes: dict[str, str] = {
        corp.corp_name: corp.corp_code
        for corp in corp_list
        if corp.stock_code
    }

    # Persist to cache for future imports
    with _CACHE_FILE.open("w", encoding="utf-8") as f:
        json.dump(company_codes, f, ensure_ascii=False, indent=2)

    print(f"[get_companies] Cached {len(company_codes)} listed companies → {_CACHE_FILE}")
    return company_codes


# ---------------------------------------------------------------------------
# Module-level constant – populated on first import
# ---------------------------------------------------------------------------
COMPANY_CODES: dict[str, str] = _load_company_codes()
