# -*- coding: utf-8 -*-
"""
JPX銘柄リスト提供モジュール
utils/constants.py の静的リストへのラッパー
"""

import sys
import os
import pandas as pd

# プロジェクトルートへのパスを追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from utils.constants import get_stock_list, get_tickers, get_sector_map, get_name_map, SECTORS

FULL_CSV_PATH = os.path.join(PROJECT_ROOT, "data", "jpx_all_stocks.csv")


def get_all_stocks() -> list[tuple[str, str, str]]:
    """
    全銘柄リストを返す
    Returns: [(ティッカー, 銘柄名, セクター), ...]
    """
    return get_stock_list()


def get_all_tickers() -> list[str]:
    """全ティッカーリストを返す"""
    return get_tickers()


def get_ticker_to_sector() -> dict[str, str]:
    """ティッカー→セクターのマッピングを返す"""
    return get_sector_map()


def get_ticker_to_name() -> dict[str, str]:
    """ティッカー→銘柄名のマッピングを返す"""
    return get_name_map()


def get_all_sectors() -> list[str]:
    """全33業種リストを返す"""
    return SECTORS


def get_stocks_by_sector(sector: str) -> list[tuple[str, str, str]]:
    """指定セクターの銘柄リストを返す"""
    return [(t, n, s) for t, n, s in get_stock_list() if s == sector]


def get_stock_count() -> int:
    """銘柄数を返す"""
    return len(get_stock_list())


def get_all_listed_stocks_df() -> pd.DataFrame:
    """
    全上場銘柄（プライム・スタンダード・グロース）のDataFrameを返す。
    CSVが存在しない場合は空のDataFrameを返す。
    Returns: DataFrame(columns=['ticker', 'name', 'sector', 'market'])
    """
    if os.path.exists(FULL_CSV_PATH):
        try:
            return pd.read_csv(FULL_CSV_PATH)
        except Exception as e:
            print(f"Error reading {FULL_CSV_PATH}: {e}")
    
    return pd.DataFrame(columns=["ticker", "name", "sector", "market"])


def get_all_listed_stocks() -> list[dict]:
    """
    全上場銘柄（プライム・スタンダード・グロース）のリストを返す。
    Returns: [{'ticker': '...', 'name': '...', 'sector': '...', 'market': '...'}, ...]
    """
    df = get_all_listed_stocks_df()
    if not df.empty:
        return df.to_dict("records")
    return []
