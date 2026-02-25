# -*- coding: utf-8 -*-
"""
テクニカル指標計算モジュール
- SMA(5, 25, 75)
- PPO (移動平均乖離率)
- RSI(14)
- 出来高急増率
"""

import pandas as pd
import numpy as np


def calculate_sma(series: pd.Series, window: int) -> pd.Series:
    """単純移動平均線（SMA）を計算する"""
    return series.rolling(window=window, min_periods=1).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI（Relative Strength Index）を計算する"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    # Wilderの移動平均（指数移動平均）
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_ppo(sma_short: pd.Series, sma_long: pd.Series) -> pd.Series:
    """
    PPO（移動平均乖離率）を計算する
    PPO = (SMA5 - SMA25) / SMA25 * 100
    """
    return ((sma_short - sma_long) / sma_long * 100).replace([np.inf, -np.inf], np.nan)


def calculate_volume_ratio(volume: pd.Series, window: int = 5) -> pd.Series:
    """
    出来高急増率を計算する
    当日出来高 / 過去5日平均出来高（当日を含まない）
    """
    # shift(1) で当日を除外し、過去5日間の平均と比較する
    avg_volume = volume.rolling(window=window, min_periods=1).mean().shift(1)
    ratio = (volume / avg_volume).replace([np.inf, -np.inf], np.nan)
    return ratio


def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    全テクニカル指標を一括計算する

    Args:
        df: 'Close'と'Volume'カラムを持つDataFrame（日付でソート済み）

    Returns:
        指標カラムが追加されたDataFrame
    """
    if df.empty or "Close" not in df.columns:
        return df

    result = df.copy()

    # SMA計算
    result["sma5"] = calculate_sma(result["Close"], 5)
    result["sma25"] = calculate_sma(result["Close"], 25)
    result["sma75"] = calculate_sma(result["Close"], 75)

    # PPO計算
    result["ppo"] = calculate_ppo(result["sma5"], result["sma25"])

    # RSI計算
    result["rsi"] = calculate_rsi(result["Close"], 14)

    # 出来高急増率計算
    if "Volume" in result.columns:
        result["volume_ratio"] = calculate_volume_ratio(result["Volume"], 5)
    else:
        result["volume_ratio"] = np.nan

    return result


def get_latest_indicators(df: pd.DataFrame) -> dict:
    """
    最新日の指標値を辞書で返す

    Returns:
        {"close": ..., "volume": ..., "rsi": ..., "sma5": ..., "sma25": ...,
         "sma75": ..., "ppo": ..., "volume_ratio": ...}
    """
    if df.empty:
        return {}

    calculated = calculate_all_indicators(df)
    if calculated.empty:
        return {}

    last_row = calculated.iloc[-1]

    return {
        "date": str(last_row.name.date()) if hasattr(last_row.name, "date") else str(last_row.name),
        "open": float(last_row.get("Open", 0)) if pd.notna(last_row.get("Open")) else None,
        "high": float(last_row.get("High", 0)) if pd.notna(last_row.get("High")) else None,
        "low": float(last_row.get("Low", 0)) if pd.notna(last_row.get("Low")) else None,
        "close": float(last_row.get("Close", 0)) if pd.notna(last_row.get("Close")) else None,
        "volume": int(last_row.get("Volume", 0)) if pd.notna(last_row.get("Volume")) else None,
        "rsi": round(float(last_row.get("rsi", 0)), 2) if pd.notna(last_row.get("rsi")) else None,
        "sma5": round(float(last_row.get("sma5", 0)), 2) if pd.notna(last_row.get("sma5")) else None,
        "sma25": round(float(last_row.get("sma25", 0)), 2) if pd.notna(last_row.get("sma25")) else None,
        "sma75": round(float(last_row.get("sma75", 0)), 2) if pd.notna(last_row.get("sma75")) else None,
        "ppo": round(float(last_row.get("ppo", 0)), 2) if pd.notna(last_row.get("ppo")) else None,
        "volume_ratio": round(float(last_row.get("volume_ratio", 0)), 2) if pd.notna(last_row.get("volume_ratio")) else None,
    }
