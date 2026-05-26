# ---------------------------------------------------------------
# 1. 분위수 생성
# ---------------------------------------------------------------
def make_size_group(df, n_bins=10):
    df = df.copy()

    def _qcut(x):
        valid = x.dropna()
        if valid.nunique() < 2:
            return pd.Series(np.nan, index=x.index)
        bins = min(n_bins, valid.nunique())
        try:
            return pd.qcut(x, q=bins, labels=False, duplicates='drop')
        except ValueError:
            return pd.Series(np.nan, index=x.index)

    df['size_group'] = df.groupby('period')['자산총계'].transform(_qcut)
    df['size_group'] = df['size_group'].fillna(-1).astype(int)
    return df


# ---------------------------------------------------------------
# 2. 계층적 중앙값 대체
# ---------------------------------------------------------------
def fill_median_hierarchical(df, cols, train_mask=None):
    df = df.copy()
    stat_src = df if train_mask is None else df.loc[train_mask]

    for col in cols:
        if col not in df.columns:
            continue

        # (a) 동일 분기 + 동일 분위수 그룹의 중앙값
        #     size_group == -1 (분위 생성 실패) 행은 (a) 단계에서 매칭되지 않음 → 다음 fallback으로 진행
        med_grp = (
            stat_src[stat_src['size_group'] != -1]
            .groupby(['period', 'size_group'])[col]
            .median()
            .rename('_fill_grp')
            .reset_index()
        )
        merged = df[['period', 'size_group']].merge(
            med_grp, on=['period', 'size_group'], how='left'
        )
        df[col] = df[col].fillna(
            pd.Series(merged['_fill_grp'].values, index=df.index)
        )

        # (b) fallback: 동일 분기 전체 중앙값
        med_period = stat_src.groupby('period')[col].median()
        df[col] = df[col].fillna(df['period'].map(med_period))

        # (c) final fallback: 컬럼 전체 중앙값
        overall = stat_src[col].median()
        if pd.notna(overall):
            df[col] = df[col].fillna(overall)

    return df


# ---------------------------------------------------------------
# 실행
# ---------------------------------------------------------------
filled = []
for name, df in target_datasets:
    df = make_size_group(df, n_bins=10)
    df = fill_median_hierarchical(df, target_columns, train_mask=None)

    remain = df[target_columns].isnull().sum().sum()
    print(f"{name} 대체 완료. 남은 결측: {remain}")
    filled.append((name, df))
