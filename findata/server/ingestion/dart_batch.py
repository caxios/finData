"""
OpenDART data-fetching entrypoint.

Runs any combination of these four modules:
  - accounts    -> MultiCompanyAccounts    (다중회사 주요계정)
  - indicators  -> MultiCompanyIndicators  (다중회사 주요 재무지표)
  - statements  -> SingleCompanyStatements (단일회사 전체 재무제표)
  - reports     -> ReportMainInfo          (정기보고서 주요정보)

Companies are loaded from ``get_companies.COMPANY_CODES`` (name -> corp_code).

Examples:
    # All modules, all companies (default)
    python application.py

    # All modules, single company
    python application.py --company samsung

    # Only one module, all companies
    python application.py --only indicators

    # Multiple specific modules
    python application.py --only accounts,indicators

    # One module, one company
    python application.py --company samsung --only indicators
"""

import argparse
import json
import logging
from pathlib import Path

# NOTE: the OpenDART classes and COMPANY_CODES are imported *lazily* inside the
# functions that use them. They pull in heavy optional deps (dart-fss, pandas),
# so importing this module must not require them — the scheduler imports this
# module even on hosts where DART deps aren't installed (it just skips the job).

logger = logging.getLogger(__name__)

WHITELIST_FILES = ['semi_companies.json', 'car_companies.json', 'ship_companies.json']
DEFAULT_WHITELIST = 'car_companies.json'
START = 2015
END = 2025
YEARS = [str(year) for year in range(START, END + 1)]


ALL_MODULES = ("accounts", "indicators", "statements", "reports")


def load_companies(name: str | None = None, whitelist_file: Path | None = None) -> dict[str, str]:
    """Build a {name: corp_code} dict from a whitelist JSON file.

    The whitelist is a JSON array of company names, e.g. ``["삼성전자", "카카오"]``.
    Each name is resolved against the full DART corporate list cached in
    ``COMPANY_CODES``.

    If ``name`` is given, ignore the whitelist and look up that single company.
    """
    from findata.dart.utils.get_companies import COMPANY_CODES

    if name is not None:
        if name not in COMPANY_CODES:
            raise KeyError(f"Company '{name}' not found in DART corporate list.")
        return {name: COMPANY_CODES[name]}

    if whitelist_file is None:
        whitelist_file = Path(__file__).parent / "companies_json" / DEFAULT_WHITELIST

    with whitelist_file.open(encoding="utf-8") as f:
        watchlist: list[str] = json.load(f)

    companies: dict[str, str] = {}
    for company_name in watchlist:
        if company_name in COMPANY_CODES:
            companies[company_name] = COMPANY_CODES[company_name]
        else:
            print(f"[warn] '{company_name}' not found in DART corporate list - skipped.")

    if not companies:
        raise SystemExit(f"No valid companies in {whitelist_file.name}.")

    return companies


def run_accounts(corp_codes: list[str], filename: str | None = None) -> None:
    from findata.dart import MultiCompanyAccounts, OpenDartError
    try:
        path = MultiCompanyAccounts().save_quarterly(
            corp_codes=corp_codes, bsns_years=YEARS, filename=filename
        )
        print(f"[ok]   multi_company_accounts -> {path}")
    except (ValueError, OpenDartError) as e:
        print(f"[err]  multi_company_accounts: {e}")


def run_indicators(corp_codes: list[str], filename: str | None = None) -> None:
    from findata.dart import MultiCompanyIndicators, OpenDartError
    try:
        path = MultiCompanyIndicators().save_quarterly(
            corp_codes=corp_codes, bsns_years=YEARS, filename=filename
        )
        print(f"[ok]   multi_company_indicators -> {path}")
    except (ValueError, OpenDartError) as e:
        print(f"[err]  multi_company_indicators: {e}")


def run_statements(companies: dict[str, str]) -> None:
    from findata.dart import SingleCompanyStatements, OpenDartError
    single = SingleCompanyStatements()
    for name, code in companies.items():
        try:
            path = single.save_quarterly(corp_code=code, bsns_years=YEARS)
            print(f"[ok]   single_company_statements [{name}] -> {path}")
        except (ValueError, OpenDartError) as e:
            print(f"[err]  single_company_statements [{name}]: {e}")


def run_reports(companies: dict[str, str]) -> None:
    from findata.dart import ReportMainInfo, OpenDartError
    report = ReportMainInfo()
    for name, code in companies.items():
        try:
            path = report.save_all(corp_code=code, bsns_years=YEARS)
            print(f"[ok]   report_main_info [{name}] -> {path}")
        except (ValueError, OpenDartError) as e:
            print(f"[err]  report_main_info [{name}]: {e}")


def main(target: str | None, modules: list[str], whitelist: str | None = None) -> None:
    whitelist_path = Path(__file__).parent / "companies_json" / whitelist if whitelist else None
    companies = load_companies(target, whitelist_path)
    corp_codes = list(companies.values())
    # When a single company is requested, default filename logic in
    # save_quarterly is fine. Otherwise tag the output by whitelist stem so
    # batches from different industries don't clobber each other.
    out_stem = None if target else (whitelist_path or Path(DEFAULT_WHITELIST)).stem

    print(f"Fetching for: {len(companies)} companies from "
          f"{'--company' if target else (whitelist or DEFAULT_WHITELIST)}")
    print(f"Modules:      {', '.join(modules)}")

    if "accounts" in modules:
        run_accounts(corp_codes, filename=f"multi_acnt_quarterly_{out_stem}" if out_stem else None)
    if "indicators" in modules:
        run_indicators(corp_codes, filename=f"multi_indx_quarterly_{out_stem}" if out_stem else None)
    if "statements" in modules:
        run_statements(companies)
    if "reports" in modules:
        run_reports(companies)


# ============================================================
# Schedulable entrypoint (plan 06 Step 3)
# ============================================================

def _resolve_corp_codes(names: list[str]) -> dict[str, str]:
    """Resolve KR company names → {name: corp_code}, skipping unknown names."""
    from findata.dart.utils.get_companies import COMPANY_CODES
    out: dict[str, str] = {}
    for name in names:
        code = COMPANY_CODES.get(name)
        if code:
            out[name] = code
        else:
            logger.warning("DART: company not found, skipping: %s", name)
    return out


def _is_quota_error(exc: Exception) -> bool:
    """Heuristic: treat OpenDART errors mentioning rate/quota limits as retryable."""
    msg = str(exc).lower()
    return any(s in msg for s in ("quota", "rate", "limit", "too many", "030", "020"))


def run_dart_refresh(
    universe: list[str] | None = None,
    modules: list[str] | None = None,
    *,
    chunk_size: int = 20,
    delay: float = 1.0,
    retries: int = 3,
    base_delay: float = 5.0,
) -> dict:
    """Refresh OpenDART data for the universe (schedulable callable).

    Stays under OpenDART's daily request cap by (a) chunking the universe so the
    run is spread out, (b) sleeping ``delay`` seconds between chunks, and
    (c) backing off exponentially when a quota error is hit (plan 06 Step 3).

    Args:
        universe:   KR company names. Defaults to the configured KR universe.
        modules:    Subset of ALL_MODULES. Defaults to all.
        chunk_size: Companies per chunk (multi-company modules run per chunk).
        delay:      Seconds to sleep between chunks.
        retries/base_delay: Backoff config for quota errors.

    Returns a summary dict.
    """
    import time as _time
    from findata.server.ingestion.universe import get_kr_universe
    from findata.server.ingestion.throttle import chunked, run_with_backoff

    names = universe if universe is not None else get_kr_universe()
    modules = modules or list(ALL_MODULES)
    companies = _resolve_corp_codes(names)
    if not companies:
        logger.warning("DART refresh: no resolvable companies in universe")
        return {"companies": 0, "chunks": 0, "modules": modules}

    items = list(companies.items())  # [(name, code), ...]
    chunks = list(chunked(items, chunk_size))
    logger.info("DART refresh: %d companies in %d chunk(s), modules=%s",
                len(items), len(chunks), modules)

    for idx, chunk in enumerate(chunks):
        chunk_companies = dict(chunk)
        corp_codes = list(chunk_companies.values())

        def _do_chunk():
            if "accounts" in modules:
                run_accounts(corp_codes)
            if "indicators" in modules:
                run_indicators(corp_codes)
            if "statements" in modules:
                run_statements(chunk_companies)
            if "reports" in modules:
                run_reports(chunk_companies)

        run_with_backoff(
            _do_chunk,
            retries=retries,
            base_delay=base_delay,
            is_retryable=_is_quota_error,
        )
        if idx < len(chunks) - 1:
            _time.sleep(delay)

    return {"companies": len(items), "chunks": len(chunks), "modules": modules}


def parse_modules(raw: str | None) -> list[str]:
    if not raw:
        return list(ALL_MODULES)
    picked = [m.strip() for m in raw.split(",") if m.strip()]
    invalid = [m for m in picked if m not in ALL_MODULES]
    if invalid:
        raise SystemExit(
            f"Invalid module(s): {invalid}. Choose from: {list(ALL_MODULES)}"
        )
    return picked


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OpenDART data.")
    parser.add_argument(
        "--company", "-c",
        help="Single company name (key in companies.json). Default: all companies.",
    )
    parser.add_argument(
        "--only", "-o",
        help=f"Comma-separated modules to run. Choices: {','.join(ALL_MODULES)}. Default: all.",
    )
    parser.add_argument(
        "--whitelist", "-w",
        choices=WHITELIST_FILES,
        help=f"Whitelist JSON file to read. Default: {DEFAULT_WHITELIST}.",
    )
    args = parser.parse_args()

    main(target=args.company, modules=parse_modules(args.only), whitelist=args.whitelist)


"""
Command	What it runs
python application.py	everything, all companies (unchanged default)
python application.py --only indicators	only multi_company_indicators, all companies
python application.py --only accounts,indicators	just the two multi-company fetchers
python application.py -c samsung -o indicators	indicators for samsung only
python application.py -c samsung	everything for samsung
"""
