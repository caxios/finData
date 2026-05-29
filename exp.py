def decile_portfolio_stats(df):
    port = (
        df.groupby(['period', 'Decile'])['Return']
        .mean()
        .unstack('Decile')
        .sort_index()
    )
    summary = pd.DataFrame({
        'cum_return': (1 + port).prod() - 1,
        'mean_return': port.mean(),
        'volatility': port.std(),
        'sharpe_ann': port.mean() / port.std() * np.sqrt(4),
        'n_periods': port.count(),
    })
    summary.index.name = 'Decile'
    return summary, port


def decile_membership(df):
    return {
        period: {int(decile): sub['corp_code'].tolist()
                 for decile, sub in g.groupby('Decile')}
        for period, g in df.groupby('period')
    }


def plot_decile_cumulative(port_ts, title):
    import matplotlib.pyplot as plt
    cum = (1 + port_ts).cumprod()
    ax = cum.plot(figsize=(10, 6), colormap='RdYlGn_r')
    ax.set_title(f"{title} — Decile Cumulative Return (quaterly rebalanced)")
    ax.set_xlabel('period')
    ax.set_ylabel('Cumulative Growth Multiple (Start = 1)')
    ax.axhline(1.0, color='gray', linewidth=0.8, linestyle='--')
    ax.legend(title='Decile', bbox_to_anchor=(1.02, 1), loc='upper left')
    plt.tight_layout()
    plt.show()
    return ax


def decile_transition_returns(df):
    d = df.sort_values(['corp_code', 'period']).copy()
    d['prev_Decile'] = d.groupby('corp_code')['Decile'].shift(1)
    d['next_Return'] = d.groupby('corp_code')['Return'].shift(-1)
    d = d.dropna(subset=['prev_Decile', 'next_Return'])
    d['decile_change'] = (d['Decile'] - d['prev_Decile']).astype(int)

    by_change = d.groupby('decile_change')['next_Return'].agg(['mean', 'median', 'std', 'count'])
    matrix = d.pivot_table(
        index='prev_Decile', columns='Decile', values='next_Return', aggfunc='mean'
    )
    return by_change, matrix


results = {}
sectors = ['car', 'semi', 'ship']
methods = ['rf_mlp', 'lasso_mlp', 'xgboost']
for sector in sectors:
    for method in methods:
        dict_key = f"{sector}_{method}"
        
        # 딕셔너리에 해당 키가 없으면 건너뜀
        if dict_key not in final_ff_dfs:
            print(f"⚠️ {dict_key} 데이터가 없어 건너뜁니다.")
            continue
            
        model_df = final_ff_dfs[dict_key].copy()
        
        # 1. 결측치 제거
        cols = ['period', 'Return', 'Mkt_RF', 'SMB', 'HML', 'Earning_Factor']
        model_df = model_df.dropna(subset=cols)
        
        # ==========================================
        # 2. 분기별 어닝 팩터 기준 10분위수(Decile) 할당
        # ==========================================
        # rank(method='first')를 사용하여 확률값이 겹쳐도 강제로 10등분하도록 처리
        # 1분위(D1): 가장 낮음(저위험) ~ 10분위(D10): 가장 높음(고위험)
        model_df['Decile'] = model_df.groupby('period')['Earning_Factor'].transform(
            lambda x: pd.qcut(x.rank(method='first'), q=10, labels=False) + 1
        )

        # ==========================================
        # 3. Decile 포트폴리오 수익률 / 변동성
        # ==========================================
        stats, port_ts = decile_portfolio_stats(model_df)
        by_change, trans_matrix = decile_transition_returns(model_df)
        members = decile_membership(model_df)

        results[dict_key] = {
            'stats': stats,
            'port_ts': port_ts,
            'by_change': by_change,
            'matrix': trans_matrix,
            'members': members,
        }

        print(f"\n=== {dict_key} Decile Portfolio ===")
        print(stats.round(4))
        print(f"\n--- {dict_key} Decile per transition Average Return ---")
        print(by_change.round(4))

        plot_decile_cumulative(port_ts, dict_key)