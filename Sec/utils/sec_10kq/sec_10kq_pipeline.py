"""
sec_10kq_pipeline.py
────────────────────
Main orchestrator for the SEC 10-K / 10-Q text extraction pipeline.

Usage:
    python sec_10kq_pipeline.py                  # default: 5 most recent per company
    python sec_10kq_pipeline.py --count 10       # 10 most recent per company
    python sec_10kq_pipeline.py --count 3 --dry  # dry-run (no DB writes)
"""

import os
import sys
import time
import argparse
import logging

# Ensure parent directory is in path so absolute imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sec_10kq.sec_10kq_rss import fetch_and_resolve
from sec_10kq.sec_10kq_parser import parse_single_filing
from sec_10kq.sec_10kq_db import save_batch, get_filing_count

logger = logging.getLogger(__name__)


# ============================================================
# Configuration
# ============================================================

from sec_cik_mapper import StockMapper

# List of tickers to track
TICKERS = ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL"]

# Dynamically map tickers to zero-padded CIKs using sec_cik_mapper
mapper = StockMapper()
ticker_to_cik = mapper.ticker_to_cik

WATCHLIST = []
for ticker in TICKERS:
    cik = ticker_to_cik.get(ticker)
    if cik:
        WATCHLIST.append((ticker, cik))
    else:
        print(f"[WARN] Could not find CIK for ticker: {ticker}")

# Default number of filings to process per company
DEFAULT_COUNT = 5

# SEC rate limit delay between filings (seconds)
FILING_DELAY = 0.3

# Database path (pointing to backend/db/)
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db")
DB_PATH = os.path.join(DB_DIR, "sec_10kq.db")


# ============================================================
# Pipeline Orchestrator
# ============================================================

def run_pipeline(count: int = DEFAULT_COUNT, dry_run: bool = False):
    """
    Run the full 10-K / 10-Q extraction pipeline for all companies
    in the watchlist.

    Args:
        count:   Max number of filings to fetch per company.
        dry_run: If True, parse but don't save to DB.
    """
    os.makedirs(DB_DIR, exist_ok=True)

    total_parsed = []
    total_start = time.time()

    print("=" * 60)
    print("SEC 10-K / 10-Q Text Extraction Pipeline")
    print(f"  Watchlist:  {len(WATCHLIST)} companies")
    print(f"  Max count:  {count} filings per company")
    print(f"  Database:   {DB_PATH}")
    print(f"  Dry run:    {dry_run}")
    print("=" * 60)

    for ticker, cik in WATCHLIST:
        print(f"\n{'─' * 50}")
        print(f"  [{ticker}] CIK: {cik}")
        print(f"{'─' * 50}")

        try:
            # Stage 1: RSS + resolve document URLs
            filings = fetch_and_resolve(cik, count=count)

            if not filings:
                print(f"  No filings found for {ticker}")
                continue

            # Stage 2-5: Download + parse each filing
            parsed_filings = []
            for filing in filings:
                if not filing.get("document_url"):
                    print(f"  [SKIP] No document URL: {filing.get('accession_number')}")
                    continue

                try:
                    result = parse_single_filing(filing)
                    parsed_filings.append(result)
                except Exception as e:
                    print(f"  [ERROR] Failed to parse {filing.get('accession_number')}: {e}")

                time.sleep(FILING_DELAY)

            # Summary for this company
            successful = [f for f in parsed_filings if f.get("sections")]
            print(f"\n  [{ticker}] Results: {len(successful)}/{len(parsed_filings)} filings parsed")

            for f in successful:
                sections = f.get("sections", {})
                found = [k for k, v in sections.items() if v is not None]
                print(f"    {f['form_type']} {f['filing_date']}: {found}")

            total_parsed.extend(parsed_filings)

        except Exception as e:
            print(f"  [FATAL] {ticker}: {e}")

    # ---- Save to DB ----
    print(f"\n{'=' * 60}")
    print("Pipeline Complete")
    print(f"  Total filings processed: {len(total_parsed)}")
    print(f"  Time elapsed: {time.time() - total_start:.1f}s")

    if dry_run:
        print("  [DRY RUN] Skipping database writes.")
        # Print a sample of what would be saved
        for f in total_parsed[:2]:
            sections = f.get("sections", {})
            if sections:
                for key, val in sections.items():
                    if val is not None:
                        preview = val[:200] if isinstance(val, str) else str(val)[:200]
                        print(f"\n  --- {f['form_type']} / {key} (preview) ---")
                        print(f"  {preview}...")
    else:
        successful = [f for f in total_parsed if f.get("sections")]
        if successful:
            inserted, skipped = save_batch(successful, DB_PATH)
            total = get_filing_count(DB_PATH)
            print(f"  Total filings in DB: {total}")
        else:
            print("  No filings to save.")

    print(f"{'=' * 60}")
    return total_parsed


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="SEC 10-K / 10-Q Text Extraction Pipeline"
    )
    parser.add_argument(
        "--count", type=int, default=DEFAULT_COUNT,
        help=f"Max filings to fetch per company (default: {DEFAULT_COUNT})"
    )
    parser.add_argument(
        "--dry", action="store_true",
        help="Dry run: parse but don't write to database"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    run_pipeline(count=args.count, dry_run=args.dry)


if __name__ == "__main__":
    main()
