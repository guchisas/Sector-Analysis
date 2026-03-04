import os
import sys
import pandas as pd
import requests
from io import BytesIO

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.update_stock_list import download_jpx_list, ALL_MARKETS, FULL_CSV_PATH

def main():
    print("Downloading JPX list...")
    jpx_df = download_jpx_list()
    
    code_col = None
    name_col = None
    sector_col = None
    market_col = None

    for col in jpx_df.columns:
        col_str = str(col).strip()
        if col_str == "コード" and code_col is None:
            code_col = col
        elif col_str == "銘柄名" and name_col is None:
            name_col = col
        elif col_str == "33業種区分" and sector_col is None:
            sector_col = col
        elif ("市場" in col_str or "上場" in col_str) and market_col is None:
            market_col = col

    all_markets_df = jpx_df[jpx_df[market_col].isin(ALL_MARKETS)] if market_col else jpx_df
    if not all_markets_df.empty:
        all_stocks_data = []
        for _, row in all_markets_df.iterrows():
            try:
                code = str(int(row[code_col]))
                ticker = f"{code}.T"
                name = str(row[name_col]) if name_col else ""
                sector = str(row[sector_col]) if sector_col else "不明"
                market = str(row[market_col]).replace("（内国株式）", "") if market_col else "不明"
                all_stocks_data.append({"ticker": ticker, "name": name, "sector": sector, "market": market})
            except (ValueError, TypeError):
                pass
        
        all_df = pd.DataFrame(all_stocks_data)
        os.makedirs(os.path.dirname(FULL_CSV_PATH), exist_ok=True)
        all_df.to_csv(FULL_CSV_PATH, index=False, encoding="utf-8-sig")
        print(f"✅ Saved {len(all_df)} stocks to {FULL_CSV_PATH}")

if __name__ == "__main__":
    main()
