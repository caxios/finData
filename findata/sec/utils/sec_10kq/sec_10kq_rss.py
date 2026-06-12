"""
sec_10kq_rss.py
Stage 1 of the 10-K / 10-Q pipeline.

Fetches filing metadata from EDGAR's submissions JSON endpoint
and constructs the primary-document URL directly from the accession
number + primary document filename.
"""

import time
import requests
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from findata.sec.const import HEADERS

REQUEST_DELAY = 0.15
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_URL = "https://data.sec.gov/submissions/{name}"
DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{primary}"

DEFAULT_FORMS = {"10-K", "10-Q"}


def _pad_cik(cik: str) -> str:
    return cik.zfill(10)


def _get_json(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return resp.json()


def _rows_from_recent(cik_padded: str, recent: dict, kept_forms: set[str]) -> list[dict]:
    """Convert a parallel-array recent block into row dicts for the given forms."""
    forms = recent.get("form", [])
    accs = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    primaries = recent.get("primaryDocument", [])

    cik_int = str(int(cik_padded))
    rows: list[dict] = []
    for i, form in enumerate(forms):
        if form not in kept_forms:
            continue
        acc = accs[i] if i < len(accs) else ""
        date = dates[i] if i < len(dates) else ""
        primary = primaries[i] if i < len(primaries) else ""
        if not (acc and primary):
            continue
        acc_nodash = acc.replace("-", "")
        doc_url = DOC_URL.format(cik_int=cik_int, acc_nodash=acc_nodash, primary=primary)
        index_url = (
            f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
            f"&CIK={cik_padded}&type={form}&dateb=&owner=include&count=40"
        )
        rows.append({
            "cik": cik_padded,
            "form_type": form,
            "filing_date": date,
            "title": f"{form} - {date}",
            "index_url": index_url,
            "accession_number": acc,
            "document_url": doc_url,
        })
    return rows


def fetch_and_resolve(
    cik: str,
    count: int = 10,
    include_archive: bool = False,
    forms: set[str] | None = None,
) -> list[dict]:
    """Fetch filing metadata for cik and return up to count rows with
    primary-document URLs already resolved.

    Args:
        cik:             Zero-padded or unpadded CIK.
        count:           Maximum number of rows to return.
        include_archive: When True, also walk filings.files for older archives.
        forms:           Set of form types to keep. Defaults to 10-K, 10-Q.

    Returns rows sorted by filing_date desc, capped to count.
    """
    kept_forms = forms if forms else DEFAULT_FORMS
    cik_padded = _pad_cik(cik)
    try:
        data = _get_json(SUBMISSIONS_URL.format(cik=cik_padded))
    except requests.RequestException as e:
        print(f"  [WARN] submissions.json fetch failed for CIK {cik_padded}: {e}")
        return []

    filings = data.get("filings", {})
    rows = _rows_from_recent(cik_padded, filings.get("recent", {}), kept_forms)

    if include_archive:
        for entry in filings.get("files", []):
            name = entry.get("name")
            if not name:
                continue
            try:
                archive = _get_json(ARCHIVE_URL.format(name=name))
            except requests.RequestException as e:
                print(f"  [WARN] archive fetch failed for {name}: {e}")
                continue
            rows.extend(_rows_from_recent(cik_padded, archive, kept_forms))
            if len(rows) >= count:
                break

    rows.sort(key=lambda r: r["filing_date"], reverse=True)
    print(f"  submissions.json: found {len(rows)} row(s) for CIK {cik_padded} "
          f"forms={sorted(kept_forms)} archive={'on' if include_archive else 'off'}")
    return rows[:count]


if __name__ == "__main__":
    results = fetch_and_resolve("0000789019", count=5)
    for r in results:
        print(f"  {r['form_type']} | {r['filing_date']} | {r['document_url']}")
