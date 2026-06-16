import sqlite3
import yfinance as yf
import os

from findata.server.db.config import INSIDER_ALL_DB, INSIDER_WATCHLIST_DB

def backfill_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all unique tickers that have a NULL market_cap
    cursor.execute("SELECT DISTINCT ticker FROM insider_trades WHERE market_cap IS NULL AND ticker != ''")
    tickers = [row[0] for row in cursor.fetchall() if row[0]]
    
    if not tickers:
        print(f"No tickers need backfilling in {db_path}.")
        return

    print(f"Found {len(tickers)} unique tickers to backfill in {db_path}.")
    
    updated_count = 0
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            market_cap = info.get("marketCap")
            if market_cap is not None:
                cursor.execute("UPDATE insider_trades SET market_cap = ? WHERE ticker = ?", (market_cap, ticker))
                print(f"Updated {ticker} with market cap: {market_cap}")
                updated_count += 1
            else:
                print(f"No market cap found for {ticker}")
        except Exception as e:
            print(f"Failed to fetch for {ticker}: {e}")
            
    conn.commit()
    conn.close()
    print(f"Finished backfilling {updated_count} tickers in {db_path}.\n")

if __name__ == "__main__":
    for db_path in [INSIDER_ALL_DB, INSIDER_WATCHLIST_DB]:
        if os.path.exists(db_path):
            print(f"Processing {db_path}...")
            backfill_db(db_path)
