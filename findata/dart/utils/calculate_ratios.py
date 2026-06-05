"""
calculate_ratios.py
──────────────────────────────────────────────────────────────
Read company_accounts_filled CSVs and compute financial ratios
defined in ratio_types.txt, plus YoY growth for every ratio.

Output: data/company_ratios/{car,semi,ship}_ratio.csv
"""

import os
import numpy as np
import pandas as pd


# ── I/O paths ────────────────────────────────────────────────
INPUT_DIR = 'data/company_accounts_filled'
OUTPUT_DIR = 'data/company_ratios'

SECTORS = {
    'car':  os.path.join(INPUT_DIR, 'car_acnt_filled.csv'),
    'semi': os.path.join(INPUT_DIR, 'semi_acnt_filled.csv'),
    'ship': os.path.join(INPUT_DIR, 'ship_acnt_filled.csv'),
}

# ── Column aliases (Korean account names in the CSV) ─────────
매출액     = '매출액'
부채총계   = '부채총계'
비유동부채 = '비유동부채'
비유동자산 = '비유동자산'
유동부채   = '유동부채'
유동자산   = '유동자산'
이익잉여금 = '이익잉여금'
자본금     = '자본금'
자본총계   = '자본총계'
자산총계   = '자산총계'


def safe_div(numerator, denominator):
    """Element-wise division; returns NaN where denominator is zero."""
    return numerator / denominator.replace(0, np.nan)


def compute_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all ratios defined in ratio_types.txt.
    Returns a new DataFrame with corp_code, period, and ratio columns.
    """
    out = df[['corp_code', 'period']].copy()

    # ── 안정성 및 건전성 지표 ──────────────────────────────
    # 12. 유동비율
    out['유동비율'] = safe_div(df[유동자산], df[유동부채]) * 100
    # 13. 부채비율
    out['부채비율'] = safe_div(df[부채총계], df[자본총계]) * 100
    # 14. 자기자본비율
    out['자기자본비율'] = safe_div(df[자본총계], df[자산총계]) * 100
    # 15. 총부채의존도
    out['총부채의존도'] = safe_div(df[부채총계], df[자산총계]) * 100
    # 16. 비유동비율
    out['비유동비율'] = safe_div(df[비유동자산], df[자본총계]) * 100
    # 17. 비유동장기적합률
    out['비유동장기적합률'] = safe_div(df[비유동자산], df[자본총계] + df[비유동부채]) * 100
    # 18. 유동부채비율
    out['유동부채비율'] = safe_div(df[유동부채], df[자본총계]) * 100
    # 19. 비유동부채비율
    out['비유동부채비율'] = safe_div(df[비유동부채], df[자본총계]) * 100
    # 20. 순운전자본비율
    out['순운전자본비율'] = safe_div(df[유동자산] - df[유동부채], df[자산총계]) * 100
    # 21. 유보율
    out['유보율'] = safe_div(df[이익잉여금], df[자본금]) * 100
    # 22. 자본금 대비 자본총계 비율
    out['자본금대비자본총계비율'] = safe_div(df[자본총계], df[자본금]) * 100
    # 23. 단기부채의존도
    out['단기부채의존도'] = safe_div(df[유동부채], df[자산총계]) * 100
    # 24. 장기부채의존도
    out['장기부채의존도'] = safe_div(df[비유동부채], df[자산총계]) * 100

    # ── 활동성 및 구조 지표 ──────────────────────────────
    # 25. 총자산회전율
    out['총자산회전율'] = safe_div(df[매출액], df[자산총계])
    # 26. 자기자본회전율
    out['자기자본회전율'] = safe_div(df[매출액], df[자본총계])
    # 27. 유동자산회전율
    out['유동자산회전율'] = safe_div(df[매출액], df[유동자산])
    # 28. 비유동자산회전율
    out['비유동자산회전율'] = safe_div(df[매출액], df[비유동자산])
    # 29. 순운전자본회전율
    nwc = df[유동자산] - df[유동부채]
    out['순운전자본회전율'] = safe_div(df[매출액], nwc)
    # 30. 타인자본회전율
    out['타인자본회전율'] = safe_div(df[매출액], df[부채총계])

    return out


def quarter_to_sortkey(period_str: str) -> tuple:
    """Convert '2021Q1' -> (2021, 1) for sorting."""
    year, q = period_str.split('Q')
    return (int(year), int(q))


def add_yoy_growth(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add YoY (Year-over-Year) growth columns for every ratio.
    YoY growth is computed by comparing the same quarter of the previous year.
    For example: 2022Q1 vs 2021Q1, 2023Q3 vs 2022Q3, etc.
    """
    ratio_cols = [c for c in df.columns if c not in ('corp_code', 'period')]

    # Parse year and quarter for alignment
    df = df.copy()
    df['_year'] = df['period'].str[:4].astype(int)
    df['_qtr']  = df['period'].str[-1].astype(int)

    # Self-merge: current row ↔ same corp, same quarter, year - 1
    prev = df[['corp_code', '_year', '_qtr'] + ratio_cols].copy()
    prev['_year'] = prev['_year'] + 1  # shift forward so it aligns with "current"
    prev = prev.rename(columns={c: f'{c}_prev' for c in ratio_cols})

    merged = df.merge(prev, on=['corp_code', '_year', '_qtr'], how='left')

    for col in ratio_cols:
        prev_col = f'{col}_prev'
        merged[f'{col}_YoY'] = safe_div(
            merged[col] - merged[prev_col], merged[prev_col].abs()
        ) * 100

    # Drop helper columns
    drop_cols = ['_year', '_qtr'] + [f'{c}_prev' for c in ratio_cols]
    merged.drop(columns=drop_cols, inplace=True)

    return merged


def process_sector(name: str, csv_path: str, out_dir: str):
    """Full pipeline for one sector."""
    print(f'\n[{name}] Reading {csv_path} ...')
    df = pd.read_csv(csv_path, encoding='utf-8-sig')
    print(f'  rows={len(df)}, companies={df["corp_code"].nunique()}')

    # Compute ratios
    ratios = compute_ratios(df)

    # Sort for consistent YoY alignment
    ratios['_sort'] = ratios['period'].apply(quarter_to_sortkey)
    ratios.sort_values(['corp_code', '_sort'], inplace=True)
    ratios.drop(columns='_sort', inplace=True)

    # Add YoY growth
    ratios = add_yoy_growth(ratios)

    # Save
    out_path = os.path.join(out_dir, f'{name}_ratio.csv')
    ratios.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f'  [ok] Saved -> {out_path}  ({len(ratios)} rows, {len(ratios.columns)} columns)')


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for sector, csv_path in SECTORS.items():
        process_sector(sector, csv_path, OUTPUT_DIR)
    print('\nDone.')


if __name__ == '__main__':
    main()
