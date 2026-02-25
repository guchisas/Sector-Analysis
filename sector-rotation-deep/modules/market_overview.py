# -*- coding: utf-8 -*-
"""
市場概況（地合い）モジュール
- 日経平均、TOPIX、グロース250、ドル円の主要指標を取得
- RSI(14)ベースの加熱感シグナル判定
- 25日移動平均線乖離率の算出
"""

import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, Optional


# 主要指数のティッカーシンボル定義
MARKET_INDICES = {
    "nikkei": {
        "ticker": "^N225",
        "name": "日経平均株価",
        "icon": "🇯🇵",
        "format": "¥{:,.0f}",
    },
    "topix": {
        "ticker": "^TPX",
        "name": "TOPIX",
        "icon": "📊",
        "format": "{:,.2f}",
    },
    "growth250": {
        "ticker": "2516.T",  # 東証グロース市場250（ETF）
        "name": "グロース250",
        "icon": "🌱",
        "format": "¥{:,.0f}",
    },
    "usdjpy": {
        "ticker": "USDJPY=X",
        "name": "ドル円",
        "icon": "💱",
        "format": "¥{:,.2f}",
    },
}


def _calculate_rsi(series: pd.Series, period: int = 14) -> float:
    """RSI(14)を計算して最新値を返す"""
    if len(series) < period + 1:
        return 50.0  # データ不足時は中立値を返す

    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    latest_rsi = rsi.iloc[-1]
    return float(latest_rsi) if pd.notna(latest_rsi) else 50.0


def _calculate_sma_deviation(series: pd.Series, window: int = 25) -> float:
    """25日移動平均線からの乖離率(%)を計算する"""
    if len(series) < window:
        return 0.0

    sma = series.rolling(window=window).mean()
    latest_sma = sma.iloc[-1]
    latest_price = series.iloc[-1]

    if pd.isna(latest_sma) or latest_sma == 0:
        return 0.0

    deviation = (latest_price - latest_sma) / latest_sma * 100
    return float(deviation)


def get_rsi_signal(rsi: float) -> dict:
    """RSI値から加熱感シグナルを判定する"""
    if rsi >= 70:
        return {
            "label": "🔥 加熱（警戒）",
            "color": "#FF4B4B",
            "level": "hot",
        }
    elif rsi <= 30:
        return {
            "label": "💧 売られすぎ（反発狙い）",
            "color": "#4C9BE8",
            "level": "cold",
        }
    else:
        return {
            "label": "⚖️ 中立",
            "color": "#888888",
            "level": "neutral",
        }


def get_sma_signal(deviation: float) -> dict:
    """SMA乖離率からシグナルを判定する"""
    if deviation >= 5.0:
        return {
            "label": "⚠️ 高値警戒",
            "color": "#FF6B6B",
        }
    elif deviation <= -5.0:
        return {
            "label": "📉 底値圏",
            "color": "#4ECDC4",
        }
    else:
        return {
            "label": "",
            "color": "#888888",
        }


def fetch_market_overview() -> Dict[str, dict]:
    """
    全主要指数のデータを取得し、シグナル情報を付与して返す

    Returns:
        {
            "nikkei": {
                "name": "日経平均株価", "icon": "🇯🇵",
                "price": 38500.0, "change": 1.25, "change_pct": 0.5,
                "rsi": 65.3, "sma_dev": 2.1,
                "signal": {"label": "⚖️ 中立", "color": "#888"},
                "sma_signal": {"label": "", "color": "#888"},
                "format": "¥{:,.0f}",
            },
            ...
        }
    """
    results = {}

    for key, info in MARKET_INDICES.items():
        try:
            # yfinanceで60日分の日足データを取得（RSI計算に必要）
            ticker = yf.Ticker(info["ticker"])
            df = ticker.history(period="3mo", interval="1d")

            if df.empty or "Close" not in df.columns:
                results[key] = _empty_result(info)
                continue

            close = df["Close"]
            latest_price = float(close.iloc[-1])

            # 前日比の計算
            if len(close) >= 2:
                prev_price = float(close.iloc[-2])
                change = latest_price - prev_price
                change_pct = (change / prev_price) * 100
            else:
                change = 0.0
                change_pct = 0.0

            # RSI(14)の計算
            rsi = _calculate_rsi(close, 14)

            # 25日SMA乖離率の計算
            sma_dev = _calculate_sma_deviation(close, 25)

            # シグナル生成
            signal = get_rsi_signal(rsi)
            sma_signal = get_sma_signal(sma_dev)

            results[key] = {
                "name": info["name"],
                "icon": info["icon"],
                "price": latest_price,
                "change": change,
                "change_pct": change_pct,
                "rsi": rsi,
                "sma_dev": sma_dev,
                "signal": signal,
                "sma_signal": sma_signal,
                "format": info["format"],
            }

        except Exception as e:
            print(f"⚠️ {info['name']} の取得に失敗: {e}")
            results[key] = _empty_result(info)

    return results


def _empty_result(info: dict) -> dict:
    """データ取得失敗時の空レスポンス"""
    return {
        "name": info["name"],
        "icon": info["icon"],
        "price": None,
        "change": 0.0,
        "change_pct": 0.0,
        "rsi": 50.0,
        "sma_dev": 0.0,
        "signal": get_rsi_signal(50.0),
        "sma_signal": get_sma_signal(0.0),
        "format": info["format"],
    }
