"""
Dispatcher: form-type → (parser, db).

Public entry point: `get_or_parse(form, accession, document_url, ...)`.
On cache miss, downloads the primary document, parses it, persists, and
returns the same shape as if it were cached.
"""

import requests
import sys
import os
from findata.core.config import SEC_DB_DIR, DART_CACHE_DIR
from typing import Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from findata.sec.const import HEADERS

from sec_filings.db import save_filing, select_filing, DB_PATHS
from sec_filings import parser_8k, parser_s4, parser_sc13, parser_144

PARSEABLE_FORMS = set(DB_PATHS.keys())


def _download(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  [WARN] download failed for {url}: {e}")
        return None


def _parse(form: str, content: str) -> dict[str, Any]:
    if form == "8-K":
        return parser_8k.parse_8k(content)
    if form == "S-4":
        return parser_s4.parse_s4(content)
    if form in ("SC 13D", "SC 13G"):
        return parser_sc13.parse_sc13(content)
    if form == "144":
        return parser_144.parse_144(content)
    raise ValueError(f"No parser for form {form}")


def get_or_parse(
    form: str,
    accession_number: str,
    document_url: str,
    cik: str | None = None,
    filing_date: str | None = None,
) -> dict[str, Any] | None:
    """Return parsed sections for `accession_number`, parsing on miss."""
    if form not in PARSEABLE_FORMS:
        return None

    cached = select_filing(form, accession_number)
    if cached:
        return cached

    content = _download(document_url)
    if not content:
        return None

    parsed = _parse(form, content)
    parsed.update({
        "cik": cik,
        "accession_number": accession_number,
        "form_type": form,
        "filing_date": filing_date,
        "document_url": document_url,
    })
    save_filing(form, parsed)
    return select_filing(form, accession_number)
