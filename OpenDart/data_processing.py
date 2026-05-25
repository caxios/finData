import os
import re

import pandas as pd


_YEAR_RE = re.compile(r"(\d{4})")


def clean_financial_data(input_csv_path: str, output_csv_path: str = None) -> pd.DataFrame:
    """Pivot OpenDART financial-statement CSVs to one row per (corp, fs_div, fiscal_year).

    - Melts the three term blocks (thstrm/frmtrm/bfefrmtrm) into long form.
    - Derives a fiscal_year int from term_dt so BS ("YYYY.12.31 현재") and
      IS ("YYYY.01.01 ~ YYYY.12.31") for the same year collapse onto one row.
    - Pivots account_nm into columns, merging BS + IS accounts on the same row.
    - Dedupes cross-report restatements (same period reported in multiple annual
      reports) via aggfunc='first'.
    """
    df = pd.read_csv(input_csv_path)

    if "account_nm" not in df.columns or "thstrm_amount" not in df.columns:
        if output_csv_path and input_csv_path != output_csv_path:
            df.to_csv(output_csv_path, index=False, encoding="utf-8-sig")
        return df

    id_vars = [
        "corp_code", "stock_code", "fs_div", "fs_nm", "account_nm",
    ]
    id_vars = [c for c in id_vars if c in df.columns]

    term_mappings = [
        ("thstrm_nm", "thstrm_dt", "thstrm_amount"),
        ("frmtrm_nm", "frmtrm_dt", "frmtrm_amount"),
        ("bfefrmtrm_nm", "bfefrmtrm_dt", "bfefrmtrm_amount"),
    ]

    term_dfs = []
    for nm_col, dt_col, amt_col in term_mappings:
        if nm_col in df.columns and dt_col in df.columns and amt_col in df.columns:
            term_df = df[id_vars + [nm_col, dt_col, amt_col]].copy()
            term_df.rename(
                columns={nm_col: "term_nm", dt_col: "term_dt", amt_col: "amount"},
                inplace=True,
            )
            term_dfs.append(term_df)

    melted_df = pd.concat(term_dfs, ignore_index=True)

    melted_df["amount"] = (
        melted_df["amount"].astype(str).str.replace(",", "").str.strip()
    )
    melted_df["amount"] = pd.to_numeric(melted_df["amount"], errors="coerce")

    melted_df["fiscal_year"] = (
        melted_df["term_dt"].astype(str).str.extract(_YEAR_RE.pattern, expand=False)
    )
    melted_df["fiscal_year"] = pd.to_numeric(melted_df["fiscal_year"], errors="coerce")

    melted_df = melted_df.dropna(subset=["amount", "term_nm", "fiscal_year"])
    melted_df["fiscal_year"] = melted_df["fiscal_year"].astype(int)

    pivot_index = [c for c in ["corp_code", "stock_code", "fs_div", "fs_nm", "fiscal_year"] if c in melted_df.columns]

    pivoted_df = melted_df.pivot_table(
        index=pivot_index,
        columns="account_nm",
        values="amount",
        aggfunc="first",
    ).reset_index()

    pivoted_df.columns.name = None

    sort_cols = [c for c in ["corp_code", "fs_div", "fiscal_year"] if c in pivoted_df.columns]
    if sort_cols:
        pivoted_df = pivoted_df.sort_values(by=sort_cols).reset_index(drop=True)

    if output_csv_path:
        os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
        pivoted_df.to_csv(output_csv_path, index=False, encoding="utf-8-sig")

    return pivoted_df
