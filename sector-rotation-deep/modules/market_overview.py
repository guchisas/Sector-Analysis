# -*- coding: utf-8 -*-
"""
市場概況（地合い）モジュール
- 日経平均、TOPIX、グロース250、ドル円の主要指標を取得
- RSI(14)ベースの加熱感シグナル判定
- 25日移動平均線乖離率の算出
- HTML/CSS Gridレスポンシブパネル出力
"""

import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, Optional


# 主要指数のティッカーシンボル定義
MARKET_INDICES = {
    "nikkei": {
        "ticker": "^N225",
        "name": "日経平均",
        "icon": "🇯🇵",
        "format": "¥{:,.0f}",
    },
    "topix": {
        "ticker": "1306.T",  # TOPIX連動ETF（指数^TPXは取得不安定のためETF代用）
        "name": "TOPIX",
        "icon": "📊",
        "format": "¥{:,.1f}",
    },
    "growth250": {
        "ticker": "2516.T",  # 東証グロース市場250指数（ETF）
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
        return 50.0

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

    return float((latest_price - latest_sma) / latest_sma * 100)


def _get_signal_class_and_label(rsi: float, sma_dev: float) -> tuple:
    """RSIとSMA乖離率から、CSSクラス名とシグナルラベルを返す"""
    if rsi >= 70 or sma_dev >= 5.0:
        return "signal-hot", "🔥 加熱"
    elif rsi <= 30 or sma_dev <= -5.0:
        return "signal-cold", "💧 売られすぎ"
    else:
        return "signal-neutral", "⚖️ 中立"


def fetch_market_overview() -> Dict[str, dict]:
    """全主要指数のデータを取得し、シグナル情報を付与して返す"""
    results = {}

    for key, info in MARKET_INDICES.items():
        try:
            ticker = yf.Ticker(info["ticker"])
            df = ticker.history(period="3mo", interval="1d")

            if df.empty or "Close" not in df.columns:
                results[key] = _empty_result(info)
                continue

            close = df["Close"]
            latest_price = float(close.iloc[-1])

            # 前日比
            if len(close) >= 2:
                prev_price = float(close.iloc[-2])
                change = latest_price - prev_price
                change_pct = (change / prev_price) * 100
            else:
                change, change_pct = 0.0, 0.0

            rsi = _calculate_rsi(close, 14)
            sma_dev = _calculate_sma_deviation(close, 25)
            signal_class, signal_label = _get_signal_class_and_label(rsi, sma_dev)

            results[key] = {
                "name": info["name"],
                "icon": info["icon"],
                "price": latest_price,
                "change": change,
                "change_pct": change_pct,
                "rsi": rsi,
                "sma_dev": sma_dev,
                "signal_class": signal_class,
                "signal_label": signal_label,
                "format": info["format"],
                # ミニチャート用: 過去1ヶ月分の終値を日付付きで返す
                "history_1m": list(close.tail(22).values),
                "history_dates": [d.strftime("%m/%d") for d in close.tail(22).index],
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
        "signal_class": "signal-neutral",
        "signal_label": "取得不可",
        "format": info["format"],
    }


def render_market_panel_html(market_data: Dict[str, dict]) -> str:
    """
    市場概況パネルのHTMLを生成する（CSS Gridレスポンシブ対応）
    ※ StreamlitのmarkdownパーサーはHTML中の空行で解釈を中断するため、
      空行を含まないコンパクトなHTMLを生成する
    """
    cards = []

    for key in ["nikkei", "topix", "growth250", "usdjpy"]:
        data = market_data.get(key, {})

        if data.get("price") is not None:
            price_str = data["format"].format(data["price"])
            chg = data.get("change", 0)
            chg_pct = data.get("change_pct", 0)
            chg_sign = "+" if chg >= 0 else ""
            chg_color = "#00D26A" if chg >= 0 else "#FF4B4B"
            rsi_val = data.get("rsi", 50)
            sma_dev = data.get("sma_dev", 0)
            signal_class = data.get("signal_class", "signal-neutral")
            signal_label = data.get("signal_label", "⚖️ 中立")

            if rsi_val >= 70:
                bar_color = "#FF4B4B"
            elif rsi_val <= 30:
                bar_color = "#4C9BE8"
            else:
                bar_color = "#00D26A"

            rsi_pct = min(max(rsi_val, 0), 100)
            icon = data.get("icon", "")
            name = data.get("name", "")
            chg_str = f"{chg_sign}{chg:,.2f} ({chg_sign}{chg_pct:.2f}%)"
            rsi_text = f"RSI(14): {rsi_val:.1f} ｜ 乖離率: {sma_dev:+.1f}%"

            # 空行を一切含めずHTMLを構築
            card = (
                f'<div class="market-card {signal_class}">'
                f'<div class="mc-name">{icon} {name}</div>'
                f'<div class="mc-price">{price_str}</div>'
                f'<div class="mc-change" style="color:{chg_color};">{chg_str}</div>'
                f'<span class="mc-signal-badge {signal_class}">{signal_label}</span>'
                f'<div class="mc-rsi-bar"><div class="mc-rsi-fill" style="width:{rsi_pct:.0f}%;background:{bar_color};"></div></div>'
                f'<div class="mc-rsi-text">{rsi_text}</div>'
                f'</div>'
            )
        else:
            icon = data.get("icon", "")
            name = data.get("name", "")
            card = (
                f'<div class="market-card signal-neutral">'
                f'<div class="mc-name">{icon} {name}</div>'
                f'<div class="mc-price" style="color:#555;">取得不可</div>'
                f'<div class="mc-change" style="color:#555;">---</div>'
                f'</div>'
            )
        cards.append(card)

    return f'<div class="market-grid">{"".join(cards)}</div>'
