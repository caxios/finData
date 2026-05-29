import pandas as pd
import FinanceDataReader as fdr
from tqdm import tqdm
import time

# 주식 수익률을 가져온다(분기 별 수익률)

RF_QUARTERLY = 0.035 / 4
START, END = '2020', '2026-05-28'

SECTORS = {
    'car':  'data/multi_company_indicators/multi_indx_quarterly_car_companies.csv',
    'semi': 'data/multi_company_indicators/multi_indx_quarterly_semi_companies.csv',
    'ship': 'data/multi_company_indicators/multi_indx_quarterly_ship_companies.csv',
}


def load_codes(csv_path):
    df = pd.read_csv(csv_path)
    df['stock_code'] = df['stock_code'].astype(str).str.zfill(6)
    df['corp_code'] = df['corp_code'].astype(str).str.zfill(8)
    mapping = df.drop_duplicates('stock_code').set_index('stock_code')['corp_code'].to_dict()
    return mapping


def fetch_stock_returns(stock_code, corp_code):
    df_price = fdr.DataReader(stock_code, START, END)
    if df_price.empty:
        return None

    quarterly_close = df_price['Close'].resample('QE').last()
    df_ret = quarterly_close.pct_change().to_frame(name='Return')
    df_ret.index = df_ret.index.to_period('Q').astype(str)
    df_ret.index.name = 'period'
    df_ret['corp_code'] = corp_code
    # df_ret['Ex_Return'] = df_ret['Return'] - RF_QUARTERLY
    # df_ret['Next_Ex_Return'] = df_ret['Ex_Return'].shift(-1)
    return df_ret.dropna()


def get_bulk_quarterly_returns(code_mapping, desc='Fetching'):
    frames = []
    for stock_code, corp_code in tqdm(code_mapping.items(), desc=desc):
        try:
            df_ret = fetch_stock_returns(stock_code, corp_code)
            if df_ret is not None and not df_ret.empty:
                frames.append(df_ret)
            time.sleep(0.1)
        except Exception as e:
            print(f"Error [{stock_code}]: {e}")
    return pd.concat(frames) if frames else pd.DataFrame()


def main():
    results = {}
    for sector, csv_path in SECTORS.items():
        code_mapping = load_codes(csv_path)
        print(f"\n[{sector}] {len(code_mapping)} tickers")
        results[sector] = get_bulk_quarterly_returns(code_mapping, desc=f"{sector} prices")
        out_path = f"quarterly_returns_{sector}.csv"
        results[sector].to_csv(out_path, encoding='utf-8-sig')
        print(f"Saved -> {out_path}")

    print("\n[car] head:")
    print(results['car'].head())
    return results


if __name__ == '__main__':
    main()
