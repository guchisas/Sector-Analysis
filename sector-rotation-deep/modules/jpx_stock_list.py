# -*- coding: utf-8 -*-
"""
JPX銘柄リスト提供モジュール
utils/constants.py の静的リストへのラッパー
"""

import sys
import os

# プロジェクトルートへのパスを追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.constants import get_stock_list, get_tickers, get_sector_map, get_name_map, SECTORS


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
