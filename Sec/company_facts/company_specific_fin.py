"""
Fetch a single company's XBRL facts from SEC EDGAR and persist to SQLite.

Public surface:
    fetch_and_save(ticker, db_path)  -> int   number of fact rows inserted
    get_company_facts(ticker)        -> dict | None   raw EDGAR JSON
"""
import requests

from const import HEADERS
from .company_facts_db import save_company_facts


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def _resolve_cik(ticker: str) -> str | None:
    response = requests.get(SEC_TICKERS_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    for item in response.json().values():
        if item.get("ticker") == ticker.upper():
            return str(item["cik_str"]).zfill(10)
    return None


def get_company_facts(ticker: str) -> dict | None:
    """Return raw companyfacts JSON for `ticker`, or None if unknown / missing."""
    cik = _resolve_cik(ticker)
    if not cik:
        return None

    facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    response = requests.get(facts_url, headers=HEADERS, timeout=60)
    if response.status_code != 200:
        return None
    return response.json()


def fetch_and_save(ticker: str, db_path: str) -> int:
    """
    Fetch companyfacts from SEC EDGAR for `ticker` and persist to `db_path`.

    Returns the number of fact rows inserted (0 if ticker unknown or no facts).
    """
    facts = get_company_facts(ticker)
    if not facts:
        return 0
    inserted, _ = save_company_facts(facts, db_path, ticker=ticker.upper())
    return inserted
