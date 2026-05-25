"""
OpenDART data-fetching examples.

Demonstrates single-year and multi-year usage of all three modules:
  - MultiCompanyAccounts    (다중회사 주요계정)
  - SingleCompanyStatements (단일회사 전체 재무제표)
  - ReportMainInfo          (정기보고서 주요정보, 30 endpoints)
"""

from OpenDart import (
    MultiCompanyAccounts,
    SingleCompanyStatements,
    ReportMainInfo,
)

# Sample corp_codes
SAMSUNG = "00126380"
SK_HYNIX = "00164779"

YEARS = ["2021", "2022", "2023", "2024", "2025"]


# ---------------------------------------------------------------------------
# 1. 다중회사 주요계정 (Multi-Company Key Accounts)
# ---------------------------------------------------------------------------
multi = MultiCompanyAccounts()

# Single year
multi.save(
    corp_codes=[SAMSUNG, SK_HYNIX],
    bsns_year="2024",
    fmt="csv",
)
# → data/multi_company_accounts/multi_acnt_00126380_00164779_2024_11011.csv

# Multi-year (one combined file)
multi.save_years(
    corp_codes=[SAMSUNG, SK_HYNIX],
    bsns_years=YEARS,
    fmt="csv",
)
# → data/multi_company_accounts/multi_acnt_00126380_00164779_2021-2024_11011.csv


# ---------------------------------------------------------------------------
# 2. 단일회사 전체 재무제표 (Single Company Full Statements)
# ---------------------------------------------------------------------------
single = SingleCompanyStatements()

# Single year — all statements
single.save(corp_code=SAMSUNG, bsns_year="2024", fmt="json")
# → data/single_company_statements/single_all_00126380_2024_11011_CFS.json

# Single year — just income statement
single.save_income_statement(corp_code=SAMSUNG, bsns_year="2024", fmt="csv")
# → data/single_company_statements/IS_00126380_2024_11011_CFS.csv

# Multi-year — all statements merged
single.save_years(corp_code=SAMSUNG, bsns_years=YEARS, fmt="csv")
# → data/single_company_statements/single_all_00126380_2021-2024_11011_CFS.csv


# ---------------------------------------------------------------------------
# 3. 정기보고서 주요정보 (Report Main Info — 30 endpoints)
# ---------------------------------------------------------------------------
report = ReportMainInfo()

# Single year — named wrapper
report.save_dividend(corp_code=SAMSUNG, bsns_year="2024", fmt="csv")
# → data/report_main_info/dividend_00126380_2024_11011.csv

# Single year — generic form
report.save(
    "major_shareholder",
    corp_code=SAMSUNG,
    bsns_year="2024",
    fmt="csv",
)

# Multi-year — fetch a few key endpoints across multiple years
for endpoint in ("dividend", "major_shareholder", "employees", "executives"):
    report.save_years(
        endpoint,
        corp_code=SAMSUNG,
        bsns_years=YEARS,
        fmt="csv",
    )
    # → data/report_main_info/{endpoint}_00126380_2021-2024_11011.csv

# Bulk: pull every available endpoint for one company × multi-year
# (endpoints with no data raise ValueError from save_data — skip them)
for endpoint in report.endpoints():
    try:
        report.save_years(
            endpoint,
            corp_code=SAMSUNG,
            bsns_years=YEARS,
            fmt="csv",
        )
    except ValueError:
        print(f"[skip] {endpoint}: no data across {YEARS}")
