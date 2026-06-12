import time
import json
import requests
from bs4 import BeautifulSoup
from findata.sec.utils.form4.form4_parser import parse_form4, HEADERS
from findata.sec._cik import lookup_cik as _lookup_cik


# ============================================================
# Configuration
# ============================================================

WATCHLIST = ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL"]

# 회사당 가져올 최근 filing 수
FILINGS_PER_COMPANY = 5

# SEC rate limit (max 10 req/s)
REQUEST_DELAY = 0.2


# ============================================================
# Watchlist-specific: fetch filings for a single company
# ============================================================
def fetch_filings(cik, count=FILINGS_PER_COMPANY):
    """
    Fetch recent Form 4 filings for a company from EDGAR's Atom feed.

    `cik` MUST be a numeric CIK (string or int). EDGAR's browse-edgar
    sometimes accepts ticker symbols in the CIK= slot, but unreliably —
    callers should resolve the ticker to a CIK first (see
    agents.data_loader._lookup_cik).
    """
    cik_str = str(cik).lstrip("0") or "0"
    url = (
        "https://www.sec.gov/cgi-bin/browse-edgar"
        f"?action=getcompany&CIK={cik_str}&type=4&dateb="
        f"&owner=include&count={count}&search_text=&action=getcompany&output=atom"
    )

    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY)

    soup = BeautifulSoup(resp.content, "xml")
    entries = soup.find_all("entry")

    filings = []
    for entry in entries:
        category = entry.find("category")
        form_type = category.get("term", "") if category else ""
        if form_type not in ("4", "4/A"):
            continue

        filings.append({
            "title": entry.title.text if entry.title else "",
            "link": entry.link["href"] if entry.link else "",
            "updated": entry.updated.text if entry.updated else "",
            "form_type": form_type,
        })

    return filings


# ============================================================
# Per-ticker entry point (works for any ticker, not just WATCHLIST)
# ============================================================
def parse_form4_for_ticker(ticker, count=FILINGS_PER_COMPANY, delay=REQUEST_DELAY):
    """Fetch + parse recent Form 4 filings for any ticker.

    Returns the same list-of-dicts shape that save_to_db expects. Empty list
    if the ticker can't be resolved to a CIK.
    """
    cik, _ = _lookup_cik(ticker)
    if not cik:
        return []
    filings = fetch_filings(cik, count=count)
    results = []
    for item in filings:
        link = item.get("link")
        if not link:
            continue
        try:
            parsed = parse_form4(link)
            parsed["rss_meta"] = {
                "title":     item.get("title"),
                "form_type": item.get("form_type"),
                "updated":   item.get("updated"),
            }
            results.append(parsed)
        except Exception as e:
            print(f"  [WARN] Failed to parse {link}: {e}")
        time.sleep(delay)
    return results


# ============================================================
# Main: fetch per-company filings, then parse with form4_parser
# ============================================================
def parse_all_form4_from_watchlist(delay=REQUEST_DELAY, count=FILINGS_PER_COMPANY):
    """
    Watchlist의 각 종목에 대해 최근 Form 4 filing을 가져오고,
    form4_parser.parse_form4()로 파싱합니다.
    """
    all_results = {}

    for ticker in WATCHLIST:
        print(f"\n--- {ticker} ---")

        try:
            cik, _ = _lookup_cik(ticker)
            if not cik:
                print(f"  [ERROR] {ticker}: CIK not found, skipping")
                continue
            filings = fetch_filings(cik, count=count)
            print(f"  Found {len(filings)} recent Form 4 filing(s)")

            results = []
            for item in filings:
                link = item.get("link")
                if not link:
                    continue
                try:
                    parsed = parse_form4(link)
                    parsed["rss_meta"] = {
                        "title":     item.get("title"),
                        "form_type": item.get("form_type"),
                        "updated":   item.get("updated"),
                    }
                    results.append(parsed)
                except Exception as e:
                    print(f"  [WARN] Failed to parse {link}: {e}")
                time.sleep(delay)

            all_results[ticker] = results

        except Exception as e:
            print(f"  [ERROR] {ticker}: {e}")

    return all_results
