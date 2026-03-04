# -*- coding: utf-8 -*-
"""
yfinanceを使用した市場データ取得モジュール
- 50銘柄単位のバッチ処理
- 最大3回の自動リトライ（指数バックオフ）
- 失敗銘柄スキップ
"""

import time
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


BATCH_SIZE = 50       # 1回のリクエストで取得する銘柄数
MAX_RETRIES = 3       # 最大リトライ回数
RETRY_DELAY = 2       # リトライ間隔（秒、指数バックオフの基準）


def fetch_batch(tickers: list[str], period: str = "1mo", interval: str = "1d") -> dict[str, pd.DataFrame]:
    """
    銘柄リストのデータを一括取得する
    失敗時は最大3回リトライ（指数バックオフ）
    """
    result = {}
    ticker_str = " ".join(tickers)

    for attempt in range(MAX_RETRIES):
        try:
            data = yf.download(
                ticker_str,
                period=period,
                interval=interval,
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )

            if data.empty:
                raise ValueError("空のデータが返されました")

            # 単一銘柄の場合の処理
            if len(tickers) == 1:
                ticker = tickers[0]
                df = data.copy()
                if not df.empty:
                    # マルチインデックスのカラムをフラット化
                    if isinstance(df.columns, pd.MultiIndex):
                        target_level = 0
                        for level in range(df.columns.nlevels):
                            vals = [str(x).lower() for x in df.columns.get_level_values(level)]
                            if "close" in vals or "open" in vals:
                                target_level = level
                                break
                        df.columns = df.columns.get_level_values(target_level)
                    
                    # 小文字カラム名があれば大文字(Title Case)に統一
                    rename_map = {c: str(c).capitalize() for c in df.columns if str(c).lower() in ["open", "high", "low", "close", "volume"]}
                    if rename_map:
                        df = df.rename(columns=rename_map)
                        
                    result[ticker] = df
            else:
                # 複数銘柄: カラムがマルチインデックス (ticker, field)
                if isinstance(data.columns, pd.MultiIndex):
                    for ticker in tickers:
                        try:
                            ticker_data = data.xs(ticker, level="Ticker", axis=1)
                            if not ticker_data.empty and ticker_data.dropna(how="all").shape[0] > 0:
                                result[ticker] = ticker_data.dropna(how="all")
                        except (KeyError, Exception):
                            pass
                else:
                    # フラットカラムの場合（単一銘柄がダウンロードされた可能性）
                    if not data.empty:
                        result[tickers[0]] = data

            return result

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = RETRY_DELAY * (2 ** attempt)
                time.sleep(wait_time)
            else:
                # 最終リトライ失敗: 個別取得にフォールバック
                for ticker in tickers:
                    try:
                        single_data = yf.download(
                            ticker,
                            period=period,
                            interval=interval,
                            auto_adjust=True,
                            progress=False,
                        )
                        if isinstance(single_data.columns, pd.MultiIndex):
                            target_level = 0
                            for level in range(single_data.columns.nlevels):
                                vals = [str(x).lower() for x in single_data.columns.get_level_values(level)]
                                if "close" in vals or "open" in vals:
                                    target_level = level
                                    break
                            single_data.columns = single_data.columns.get_level_values(target_level)
                            
                        # 小文字カラム名があれば大文字(Title Case)に統一
                        rename_map = {c: str(c).capitalize() for c in single_data.columns if str(c).lower() in ["open", "high", "low", "close", "volume"]}
                        if rename_map:
                            single_data = single_data.rename(columns=rename_map)

                        if not single_data.empty:
                            result[ticker] = single_data
                    except Exception:
                        pass  # 失敗銘柄はスキップ

    return result


def fetch_all_stocks(
    tickers: list[str],
    period: str = "1mo", # 20日間の履歴を取得するため1moに変更
    progress_callback=None,
) -> dict[str, pd.DataFrame]:
    """
    全銘柄データを50銘柄ずつバッチ取得する

    Args:
        tickers: ティッカーシンボルのリスト
        period: 取得期間（例: "3mo", "6mo", "1y"）
        progress_callback: 進捗コールバック関数（current, total を引数に取る）

    Returns:
        {ティッカー: DataFrame} の辞書
    """
    all_data = {}
    total = len(tickers)

    for i in range(0, total, BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

        # 進捗コールバック呼び出し
        if progress_callback:
            progress_callback(i, total)

        batch_result = fetch_batch(batch, period=period)
        all_data.update(batch_result)

        # レート制限回避のためのウェイト
        if i + BATCH_SIZE < total:
            time.sleep(1)

    # 最終進捗
    if progress_callback:
        progress_callback(total, total)

    return all_data


def fetch_with_streamlit_progress(
    tickers: list[str],
    period: str = "1mo", # 20日間の履歴を取得するため1moに変更
) -> dict[str, pd.DataFrame]:
    """
    Streamlit UIに進捗バーを表示しながらデータを取得する
    """
    import streamlit as st  # Streamlit依存の主要処理は選延インポートに
    progress_bar = st.progress(0)
    status_text = st.empty()

    def update_progress(current, total):
        if total > 0:
            progress = current / total
            progress_bar.progress(progress)
            status_text.text(f"📊 データ取得中... {current}/{total} 銘柄 ({progress:.0%})")

    result = fetch_all_stocks(tickers, period=period, progress_callback=update_progress)

    progress_bar.progress(1.0)
    status_text.text(f"✅ {len(result)}/{len(tickers)} 銘柄のデータを取得しました")
    time.sleep(1)
    progress_bar.empty()
    status_text.empty()

    return result


def fetch_fundamentals(tickers: list[str]) -> list[dict]:
    """
    指定したティッカーリストのファンダメンタルズ（PER, PBR, 時価総額）を取得する
    YFinanceのinfo属性を使用するため、取得にはある程度時間がかかる点に注意。
    
    Returns:
        [{"ticker": "...", "name": "...", "sector": "...", "per": 10.5, "pbr": 1.2, "market_cap": 10000000, "updated_at": "..."}]
    """
    results = []
    
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            
            per = info.get('trailingPE')
            if per is None:
                per = info.get('forwardPE')
                
            pbr = info.get('priceToBook')
            market_cap = info.get('marketCap')
            
            # 最低限のデータが取得できた場合のみリストに追加
            if per is not None or pbr is not None or market_cap is not None:
                results.append({
                    "ticker": ticker,
                    "name": info.get("longName", ""),
                    "sector": info.get("sector", ""),
                    "per": float(per) if per is not None else None,
                    "pbr": float(pbr) if pbr is not None else None,
                    "market_cap": float(market_cap) if market_cap is not None else None,
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
        except Exception:
            pass
            
    return results
