"""
fetch_data.py — Unified financial data fetcher for Korean and US markets.

Fetches company financial data from both the Korean DART system (OpenDart)
and the US SEC EDGAR system using the existing API clients in this project.

Usage:
    # Fetch both KR and US data (default whitelists)
    python fetch_data.py

    # Fetch only Korean data
    python fetch_data.py --market kr

    # Fetch only US data for a specific ticker
    python fetch_data.py --market us --us-ticker AAPL

    # Fetch Korean data for a specific company
    python fetch_data.py --market kr --kr-company 현대차

    # Fetch both, with a specific Korean whitelist
    python fetch_data.py --kr-whitelist semi_companies.json

    # Fetch US data for multiple tickers
    python fetch_data.py --market us --us-ticker AAPL,MSFT,TSLA

    # Choose which OpenDart modules to run
    python fetch_data.py --market kr --kr-modules accounts,indicators
"""

import argparse
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# The OpenDart and Sec directories have been migrated into the `findata` package.
# Ensure you run `pip install -e .` to install the package locally.
PROJECT_ROOT = Path(__file__).resolve().parent
from findata.sec.company_data import get_company_data, TickerNotFound, SECRateLimit
from findata.core.config import GENERAL_DATA_DIR



# ---------------------------------------------------------------------------
# Korean (OpenDart) fetcher
# ---------------------------------------------------------------------------
KR_ALL_MODULES = ("accounts", "indicators", "statements", "reports")
KR_WHITELIST_DIR = PROJECT_ROOT / "companies_json"
KR_DEFAULT_WHITELIST = "car_companies.json"
KR_START_YEAR = 2015
KR_END_YEAR = 2025
KR_YEARS = [str(y) for y in range(KR_START_YEAR, KR_END_YEAR + 1)]


def fetch_korean_data(
    company_name: str | None = None,
    whitelist: str = KR_DEFAULT_WHITELIST,
    modules: list[str] | None = None,
) -> None:
    """Fetch financial data from the Korean DART system."""
    from findata.dart import (
        MultiCompanyAccounts,
        MultiCompanyIndicators,
        SingleCompanyStatements,
        ReportMainInfo,
        OpenDartError,
    )
    from findata.dart.utils.get_companies import COMPANY_CODES

    modules = modules or list(KR_ALL_MODULES)

    # --- Resolve companies ---
    if company_name:
        if company_name not in COMPANY_CODES:
            print(f"  [err] Company '{company_name}' not found in DART corporate list.")
            return
        companies = {company_name: COMPANY_CODES[company_name]}
    else:
        whitelist_path = KR_WHITELIST_DIR / whitelist
        if not whitelist_path.exists():
            print(f"  [err] Whitelist file not found: {whitelist_path}")
            return
        with whitelist_path.open(encoding="utf-8") as f:
            watchlist: list[str] = json.load(f)
        companies = {}
        for name in watchlist:
            if name in COMPANY_CODES:
                companies[name] = COMPANY_CODES[name]
            else:
                print(f"  [warn] '{name}' not found in DART corporate list — skipped.")
        if not companies:
            print(f"  [err] No valid companies found in {whitelist}.")
            return

    corp_codes = list(companies.values())
    out_stem = None if company_name else Path(whitelist).stem

    print(f"  Companies : {len(companies)} ({'--kr-company' if company_name else whitelist})")
    print(f"  Modules   : {', '.join(modules)}")
    print(f"  Years     : {KR_START_YEAR}–{KR_END_YEAR}")
    print()

    if "accounts" in modules:
        try:
            filename = f"multi_acnt_quarterly_{out_stem}" if out_stem else None
            path = MultiCompanyAccounts().save_quarterly(
                corp_codes=corp_codes, bsns_years=KR_YEARS, filename=filename,
            )
            print(f"  [ok]  accounts   → {path}")
        except (ValueError, OpenDartError) as e:
            print(f"  [err] accounts   : {e}")

    if "indicators" in modules:
        try:
            filename = f"multi_indx_quarterly_{out_stem}" if out_stem else None
            path = MultiCompanyIndicators().save_quarterly(
                corp_codes=corp_codes, bsns_years=KR_YEARS, filename=filename,
            )
            print(f"  [ok]  indicators → {path}")
        except (ValueError, OpenDartError) as e:
            print(f"  [err] indicators : {e}")

    if "statements" in modules:
        single = SingleCompanyStatements()
        for name, code in companies.items():
            try:
                path = single.save_quarterly(corp_code=code, bsns_years=KR_YEARS)
                print(f"  [ok]  statements [{name}] → {path}")
            except (ValueError, OpenDartError) as e:
                print(f"  [err] statements [{name}] : {e}")

    if "reports" in modules:
        report = ReportMainInfo()
        for name, code in companies.items():
            try:
                path = report.save_all(corp_code=code, bsns_years=KR_YEARS)
                print(f"  [ok]  reports    [{name}] → {path}")
            except (ValueError, OpenDartError) as e:
                print(f"  [err] reports    [{name}] : {e}")


# ---------------------------------------------------------------------------
# US (SEC) fetcher
# ---------------------------------------------------------------------------
def fetch_us_data(
    tickers: list[str],
    limit_10kq: int = 4,
    limit_form4: int = 30,
) -> None:
    """Fetch financial data from US SEC EDGAR for given tickers."""
    from company_data import get_company_data, TickerNotFound, SECRateLimit

    print(f"  Tickers     : {', '.join(tickers)}")
    print(f"  Limit 10K/Q : {limit_10kq}")
    print(f"  Limit Form4 : {limit_form4}")
    print()

    for ticker in tickers:
        ticker = ticker.strip().upper()
        print(f"  --- {ticker} ---")
        try:
            result = get_company_data(
                ticker,
                limit_10kq=limit_10kq,
                limit_form4=limit_form4,
            )
            n_filings = len(result.get("filings_10kq", []))
            n_trades = len(result.get("form4_trades", []))
            cache = result.get("cache_status", "?")
            print(f"  [ok]  {ticker}: {n_filings} filings, {n_trades} insider trades (cache: {cache})")
        except TickerNotFound:
            print(f"  [err] {ticker}: Ticker not found in SEC/CIK database.")
        except SECRateLimit as e:
            print(f"  [err] {ticker}: SEC rate limited — retry after {e.retry_after}s")
        except Exception as e:
            print(f"  [err] {ticker}: {e}")

    # Save a summary JSON for the fetched US data
    data_dir = GENERAL_DATA_DIR / "us_company_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    summary_path = data_dir / f"fetch_summary_{datetime.now():%Y%m%d_%H%M%S}.json"

    summary = {
        "fetched_at": datetime.now().isoformat(),
        "tickers": tickers,
        "note": "Raw data is cached in Sec/db/*.db SQLite databases.",
    }
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n  Summary saved → {summary_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_kr_modules(raw: str | None) -> list[str]:
    if not raw:
        return list(KR_ALL_MODULES)
    picked = [m.strip() for m in raw.split(",") if m.strip()]
    invalid = [m for m in picked if m not in KR_ALL_MODULES]
    if invalid:
        raise SystemExit(
            f"Invalid KR module(s): {invalid}. Choose from: {list(KR_ALL_MODULES)}"
        )
    return picked


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified financial data fetcher for Korean (DART) and US (SEC) markets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fetch_data.py                                  # Both markets, defaults
  python fetch_data.py --market kr                      # Korean only
  python fetch_data.py --market us --us-ticker AAPL     # US only, Apple
  python fetch_data.py --market us --us-ticker AAPL,MSFT,TSLA
  python fetch_data.py --market kr --kr-company 현대차    # Single KR company
  python fetch_data.py --kr-whitelist semi_companies.json
  python fetch_data.py --kr-modules accounts,indicators
        """,
    )

    parser.add_argument(
        "--market", "-m",
        choices=["kr", "us", "both"],
        default="both",
        help="Which market(s) to fetch. Default: both.",
    )

    # Korean options
    kr_group = parser.add_argument_group("Korean (DART) options")
    kr_group.add_argument(
        "--kr-company",
        help="Single Korean company name (e.g. 삼성전자). Default: use whitelist.",
    )
    kr_group.add_argument(
        "--kr-whitelist",
        default=KR_DEFAULT_WHITELIST,
        help=f"Whitelist JSON file in companies_json/. Default: {KR_DEFAULT_WHITELIST}.",
    )
    kr_group.add_argument(
        "--kr-modules",
        help=f"Comma-separated DART modules. Choices: {','.join(KR_ALL_MODULES)}. Default: all.",
    )

    # US options
    us_group = parser.add_argument_group("US (SEC) options")
    us_group.add_argument(
        "--us-ticker",
        help="Comma-separated US ticker symbols (e.g. AAPL,MSFT,TSLA).",
    )
    us_group.add_argument(
        "--us-limit-10kq",
        type=int,
        default=4,
        help="Number of 10-K/10-Q filings to fetch per ticker. Default: 4.",
    )
    us_group.add_argument(
        "--us-limit-form4",
        type=int,
        default=30,
        help="Number of Form 4 insider trades to fetch per ticker. Default: 30.",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  finData — Unified Financial Data Fetcher")
    print(f"  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)
    print()

    # --- Korean ---
    if args.market in ("kr", "both"):
        print("┌─────────────────────────────────────────────┐")
        print("│  🇰🇷  Korean Market (OpenDart)               │")
        print("└─────────────────────────────────────────────┘")
        fetch_korean_data(
            company_name=args.kr_company,
            whitelist=args.kr_whitelist,
            modules=parse_kr_modules(args.kr_modules),
        )
        print()

    # --- US ---
    if args.market in ("us", "both"):
        print("┌─────────────────────────────────────────────┐")
        print("│  🇺🇸  US Market (SEC EDGAR)                  │")
        print("└─────────────────────────────────────────────┘")

        if args.us_ticker:
            tickers = [t.strip() for t in args.us_ticker.split(",") if t.strip()]
        else:
            # Default US tickers when none specified
            tickers = ["AAPL", "MSFT", "TSLA"]
            print(f"  (No --us-ticker specified, using defaults: {', '.join(tickers)})")

        fetch_us_data(
            tickers=tickers,
            limit_10kq=args.us_limit_10kq,
            limit_form4=args.us_limit_form4,
        )
        print()

    print("=" * 60)
    print("  Done.")
    print("=" * 60)


if __name__ == "__main__":
    main()
