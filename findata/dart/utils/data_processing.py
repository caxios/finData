"""Helpers for reshaping OpenDART financial-statement payloads."""

import pandas as pd

# OpenDART reprt_code → quarter number
_REPRT_CODE_TO_QUARTER = {
    "11013": 1,  # 1분기
    "11012": 2,  # 반기
    "11014": 3,  # 3분기
    "11011": 4,  # 사업보고서 (annual)
}

# Optional categorical column kept in the pivot index when present.
# sj_div (BS/IS/CF/...) is deliberately excluded so all statement types
# for one (corp, period) collapse into a single row.
_OPTIONAL_INDEX_COLS = ["fs_div"] # 재무비율 계산 시 CFS의 데이터를 이용한다.


def consolidate_quarterly(items: list[dict]) -> pd.DataFrame:
    """Pivot OpenDART account items into wide quarterly format.

    Input: raw list-of-dicts from any endpoint that exposes
    ``corp_code``, ``bsns_year``, ``reprt_code``, ``account_nm``, and
    ``thstrm_amount`` (e.g. MultiCompanyAccounts, SingleCompanyStatements).

    Output: one row per (corp_code, [fs_div], [sj_div], period), with each
    unique account_nm promoted to its own column. Sorted so all rows for
    one company appear together in chronological order.
    """
    if not items:
        return pd.DataFrame()

    df = pd.DataFrame(items)

    if "fs_div" in df.columns:
        df = df[df["fs_div"] == "CFS"]
        if df.empty:
            return pd.DataFrame()

    df["quarter"] = df["reprt_code"].map(_REPRT_CODE_TO_QUARTER)
    df["period"] = df["bsns_year"].astype(str) + "Q" + df["quarter"].astype(str)

    df["amount"] = pd.to_numeric(
        df["thstrm_amount"].astype(str).str.replace(",", "").str.strip(),
        errors="coerce",
    )

    extra = [c for c in _OPTIONAL_INDEX_COLS if c in df.columns]
    index_cols = ["corp_code"] + extra + ["period"]

    pivoted = df.pivot_table(
        index=index_cols,
        columns="account_nm",
        values="amount",
        aggfunc="first",
    ).reset_index()
    pivoted.columns.name = None

    return pivoted.sort_values(index_cols).reset_index(drop=True)


def consolidate_indicators_quarterly(items: list[dict]) -> pd.DataFrame:
    """Pivot OpenDART indicator items (fnlttCmpnyIndx) into wide quarterly format.

    Input: raw list-of-dicts with ``corp_code``, ``bsns_year``, ``reprt_code``,
    ``idx_nm``, and ``idx_val``.

    Output: one row per (corp_code, period), with each ``idx_nm`` (e.g.
    ``순이익률``, ``ROE``, ``부채비율``) promoted to its own column.
    """
    if not items:
        return pd.DataFrame()

    df = pd.DataFrame(items)

    df["quarter"] = df["reprt_code"].map(_REPRT_CODE_TO_QUARTER)
    df["period"] = df["bsns_year"].astype(str) + "Q" + df["quarter"].astype(str)

    df["value"] = pd.to_numeric(
        df.get("idx_val", pd.Series(dtype=str)).astype(str).str.replace(",", "").str.strip(),
        errors="coerce",
    )

    index_cols = ["corp_code", "period"]
    if "stock_code" in df.columns:
        index_cols.insert(1, "stock_code")

    pivoted = df.pivot_table(
        index=index_cols,
        columns="idx_nm",
        values="value",
        aggfunc="first",
    ).reset_index()
    pivoted.columns.name = None

    return pivoted.sort_values(index_cols).reset_index(drop=True)
