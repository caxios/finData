from OpenDart import MultiCompanyAccounts, SingleCompanyStatements

# --- Multi-company key accounts ---
multi = MultiCompanyAccounts()  # reads API key from .env

# Option 1: Just get data as Python dicts
items = multi.get(corp_codes=["00126380", "00334624"], bsns_year="2024")

# Option 2: Fetch + save to data/ folder
path = multi.save(
    corp_codes=["00126380", "00334624"],
    bsns_year="2024",
    fmt="csv",   # or "json"
)
# → data/multi_company_accounts/multi_acnt_00126380_00334624_2024_11011.csv


# --- Single company full statements ---
single = SingleCompanyStatements()

# Save all statements
path = single.save(corp_code="00126380", bsns_year="2024", fmt="json")
# → data/single_company_statements/single_all_00126380_2024_11011_CFS.json

# Save just the income statement as CSV
path = single.save_income_statement(
    corp_code="00126380", bsns_year="2024", fmt="csv"
)
# → data/single_company_statements/IS_00126380_2024_11011_CFS.csv
