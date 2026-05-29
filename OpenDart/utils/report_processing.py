"""Helpers for reshaping report_main_info payloads.

These endpoints have heterogeneous schemas and are intrinsically multi-row
per (company, year) — e.g. one row per executive, shareholder, or
investment — so the financial-statement pivot in ``data_processing`` does
not apply. This module just produces a clean, well-ordered wide CSV.
"""

import pandas as pd

# Columns promoted to the front of the output when present.
_LEAD_COLS = ["endpoint", "corp_code", "corp_name", "bsns_year", "reprt_code"]


def consolidate_report_main_info(items: list[dict]) -> pd.DataFrame:
    """Stack heterogeneous report_main_info items into one clean DataFrame.

    Assumes each item already carries an ``endpoint`` label and an integer
    ``bsns_year`` set by the caller (the API itself sometimes returns
    Korean term-number strings like ``"제55기(감사위원)"`` in this field, so
    the caller must force-override it before calling this function).

    - Drops columns that are empty for every row.
    - Orders columns: lead metadata first, then the remaining fields sorted
      by fill rate (most-populated first) so the dense, useful columns sit
      next to the metadata instead of being scattered across 170+ slots.
    - Sorts rows by endpoint, then bsns_year.
    """
    if not items:
        return pd.DataFrame()

    df = pd.DataFrame(items).dropna(axis=1, how="all")

    lead = [c for c in _LEAD_COLS if c in df.columns]
    rest = [c for c in df.columns if c not in lead]
    rest.sort(key=lambda c: df[c].notna().sum(), reverse=True)
    df = df[lead + rest]

    sort_keys = [c for c in ("endpoint", "bsns_year") if c in df.columns]
    if sort_keys:
        df = df.sort_values(sort_keys, kind="stable").reset_index(drop=True)
    return df
