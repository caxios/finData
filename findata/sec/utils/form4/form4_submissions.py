"""
Historical Form 4 backfill via EDGAR submissions JSON (plan 05).

The ``getcompany`` Atom feed only returns the *most recent N* filings, so it
can't answer "give me MRVL's insider trades from 2019". This module uses the
EDGAR **submissions API** — ``https://data.sec.gov/submissions/CIK##########.json``
— which lists *all* of a company's filings (form type, accession, filing date),
including older shards under ``filings.files[]``. We filter to Form 4 / 4-A in
the requested date window and parse only those documents via the existing
``parse_form4``.

Layering note: this is a pure library function (returns parsed dicts); the
server layer persists them and tracks coverage.
"""

from __future__ import annotations

import time
from typing import Optional

import requests

from findata.sec._cik import lookup_cik
from findata.sec.utils.form4.form4_parser import HEADERS, parse_form4


SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SHARD_URL = "https://data.sec.gov/submissions/{name}"
ARCHIVES_TXT_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}.txt"

_FORM4_TYPES = {"4", "4/A"}


class TickerNotFound(Exception):
    """Raised when a ticker can't be resolved to a CIK."""


def _overlaps(shard: dict, date_from: str, date_to: str) -> bool:
    """True if a submissions shard's [filingFrom, filingTo] overlaps the window.

    ISO date strings compare lexicographically, so plain string comparison is
    correct here.
    """
    sfrom = shard.get("filingFrom") or "0000-01-01"
    sto = shard.get("filingTo") or "9999-12-31"
    return sfrom <= date_to and sto >= date_from


def _collect_form4_urls(
    cik_int: int,
    block: dict,
    date_from: str,
    date_to: str,
) -> list[tuple[str, str]]:
    """From a parallel-array filings block, return (filing_date, txt_url) for
    every Form 4 / 4-A whose filing date falls within [date_from, date_to]."""
    forms = block.get("form") or []
    accessions = block.get("accessionNumber") or []
    dates = block.get("filingDate") or []

    out: list[tuple[str, str]] = []
    for form, accession, fdate in zip(forms, accessions, dates):
        if form not in _FORM4_TYPES:
            continue
        if not (date_from <= fdate <= date_to):
            continue
        acc_nodash = accession.replace("-", "")
        url = ARCHIVES_TXT_URL.format(cik_int=cik_int, acc_nodash=acc_nodash)
        out.append((fdate, url))
    return out


def _get_json(url: str, timeout: int = 30) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def fetch_form4_by_period(
    ticker: str,
    date_from: str,
    date_to: str,
    *,
    delay: float = 0.2,
    limit: Optional[int] = None,
) -> list[dict]:
    """Fetch + parse all Form 4 filings for ``ticker`` filed within the window.

    Args:
        ticker:    Stock ticker (resolved to CIK).
        date_from: Inclusive lower bound, 'YYYY-MM-DD'.
        date_to:   Inclusive upper bound, 'YYYY-MM-DD'.
        delay:     Seconds between per-filing fetches (SEC fair-access).
        limit:     Optional cap on filings parsed (testing/safety).

    Returns:
        A list of parsed Form 4 dicts (``save_to_db``-shaped). Empty list if the
        company exists but filed no Form 4s in the window.

    Raises:
        TickerNotFound: if the ticker can't be resolved to a CIK.

    Note: the submissions API exposes *filing date*, not transaction date. Form
    4s are filed within ~2 business days of the transaction, so filing-date
    windowing closely matches transaction-date windowing; callers that filter on
    ``transaction_date`` may see minor boundary effects at the window edges.
    """
    cik, _ = lookup_cik(ticker)
    if not cik:
        raise TickerNotFound(f"Unknown ticker: {ticker!r}")

    cik_padded = str(cik).zfill(10)
    cik_int = int(cik)

    root = _get_json(SUBMISSIONS_URL.format(cik=cik_padded))
    filings = root.get("filings", {})

    # 1) Recent block
    urls = _collect_form4_urls(cik_int, filings.get("recent", {}), date_from, date_to)

    # 2) Older shards — only fetch those overlapping the window (pagination).
    for shard in filings.get("files", []):
        name = shard.get("name")
        if not name or not _overlaps(shard, date_from, date_to):
            continue
        try:
            shard_block = _get_json(SHARD_URL.format(name=name))
        except Exception:
            continue  # skip an unreadable shard rather than failing the whole call
        urls.extend(_collect_form4_urls(cik_int, shard_block, date_from, date_to))
        time.sleep(delay)

    if limit is not None:
        urls = urls[:limit]

    results: list[dict] = []
    for _fdate, txt_url in urls:
        try:
            results.append(parse_form4(txt_url))
        except Exception:
            # Skip an individual unparseable filing; don't abort the backfill.
            continue
        time.sleep(delay)

    return results
