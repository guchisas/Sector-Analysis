# -*- coding: utf-8 -*-
"""
セクター風向き予想モジュール (Macro Wind Forecaster)
- 米国市場の「特化型サブセクターETF」の前日比騰落率を取得
- しきい値判定により、日本の東証33業種への「追い風/逆風」を自動判定
- アメリカのティッカーや数値はUI上に公開せず、日本の業種名と要因テキストのみ出力
"""

import yfinance as yf
import streamlit as st
from typing import Dict, List, Tuple, Optional

# =====================================================================
# しきい値定義（運用テストにより微調整可能）
# =====================================================================
THRESHOLD_SEMI = 1.5       # 半導体 (SMH) しきい値 (%)
THRESHOLD_SAAS = 1.5       # SaaS/クラウド (IGV) しきい値 (%)
THRESHOLD_RESOURCE = 1.5   # 資源 (XME/COPX) しきい値 (%)
THRESHOLD_SHIPPING = 2.0   # 海運 (BDRY) しきい値 (%)
THRESHOLD_FX = 0.5         # 為替 (JPY=X) しきい値 (%)

# =====================================================================
# 監視対象ティッカー定義
# =====================================================================
US_GEAR_TICKERS = {
    "SMH":   "ヴァンエック半導体ETF",
    "IGV":   "拡張テクノロジー・ソフトウェアETF",
    "XLF":   "金融セレクトETF",
    "^TNX":  "米10年債利回り",
    "XME":   "金属・鉱業ETF",
    "COPX":  "銅ETF",
    "BDRY":  "バルク海運ETF",
    "JPY=X": "ドル円",
}


# =====================================================================
# データ取得
# =====================================================================
@st.cache_data(ttl=3600, show_spinner="🌤️ 米国サブセクターETFデータを取得中...")
def fetch_us_gear_data() -> Dict[str, Optional[float]]:
    """
    米国市場の特化型サブセクターETF・指標の前日比騰落率(%)を取得する。
    
    Returns:
        dict: ティッカーをキー、前日比騰落率(%)を値とする辞書。
              取得失敗時は値が None になる。
    """
    results = {}

    for ticker_symbol in US_GEAR_TICKERS.keys():
        try:
            ticker = yf.Ticker(ticker_symbol)
            df = ticker.history(period="5d", interval="1d")

            if df.empty or "Close" not in df.columns or len(df) < 2:
                results[ticker_symbol] = None
                continue

            close = df["Close"]
            latest = float(close.iloc[-1])
            prev = float(close.iloc[-2])

            if prev != 0:
                change_pct = ((latest - prev) / prev) * 100
            else:
                change_pct = 0.0

            results[ticker_symbol] = round(change_pct, 3)

        except Exception as e:
            print(f"⚠️ {ticker_symbol} の取得に失敗: {e}")
            results[ticker_symbol] = None

    return results


# =====================================================================
# 日米セクター翻訳エンジン（コアロジック）
# =====================================================================
def generate_wind_forecast(
    gear_data: Dict[str, Optional[float]]
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """
    米国ギアデータのしきい値判定を行い、日本の33業種への追い風/逆風リストを生成する。
    
    為替バイアスは最優先フィルターとして最後に評価され、
    他のルールの結果を上書きする可能性がある。
    
    Args:
        gear_data: fetch_us_gear_data() の戻り値
        
    Returns:
        (tailwinds, headwinds): 追い風リストと逆風リストのタプル。
        各リスト要素は {"sector": "業種名", "reason": "要因テキスト"} の辞書。
    """
    tailwinds: List[Dict[str, str]] = []
    headwinds: List[Dict[str, str]] = []

    # 安全な値取得ヘルパー（None対応）
    def _get(key: str) -> float:
        v = gear_data.get(key)
        return v if v is not None else 0.0

    smh = _get("SMH")
    igv = _get("IGV")
    xlf = _get("XLF")
    tnx = _get("^TNX")
    xme = _get("XME")
    copx = _get("COPX")
    bdry = _get("BDRY")
    jpyx = _get("JPY=X")

    # ① 半導体・ハイテク連動
    if smh >= THRESHOLD_SEMI:
        tailwinds.append({"sector": "電気機器", "reason": "米半導体株の大幅高"})
        tailwinds.append({"sector": "精密機器", "reason": "米半導体株の大幅高"})
    elif smh <= -THRESHOLD_SEMI:
        headwinds.append({"sector": "電気機器", "reason": "米半導体株の大幅安"})
        headwinds.append({"sector": "精密機器", "reason": "米半導体株の大幅安"})

    # ② ソフトウェア・グロース連動
    if igv >= THRESHOLD_SAAS:
        tailwinds.append({"sector": "情報・通信業", "reason": "米SaaS・クラウド株への資金流入"})
        tailwinds.append({"sector": "サービス業", "reason": "米SaaS・クラウド株への資金流入"})
    elif igv <= -THRESHOLD_SAAS:
        headwinds.append({"sector": "情報・通信業", "reason": "グロース株へのリスクオフ警戒"})
        headwinds.append({"sector": "サービス業", "reason": "グロース株へのリスクオフ警戒"})

    # ③ 金融・金利連動（XLFと^TNXが同方向に動く場合のみ）
    if xlf > 0 and tnx > 0:
        tailwinds.append({"sector": "銀行業", "reason": "米金利上昇と金融株高"})
        tailwinds.append({"sector": "保険業", "reason": "米金利上昇と金融株高"})
    elif xlf < 0 and tnx < 0:
        headwinds.append({"sector": "銀行業", "reason": "米金利低下による利ざや縮小懸念"})
        headwinds.append({"sector": "保険業", "reason": "米金利低下による利ざや縮小懸念"})

    # ④ 資源・市況連動（XMEまたはCOPXのどちらかがしきい値超え）
    if xme >= THRESHOLD_RESOURCE or copx >= THRESHOLD_RESOURCE:
        tailwinds.append({"sector": "非鉄金属", "reason": "グローバル資源価格・関連株の上昇"})
        tailwinds.append({"sector": "鉱業", "reason": "グローバル資源価格・関連株の上昇"})
        tailwinds.append({"sector": "卸売業", "reason": "グローバル資源価格・関連株の上昇"})

    # ⑤ 海運連動
    if bdry >= THRESHOLD_SHIPPING:
        tailwinds.append({"sector": "海運業", "reason": "グローバルばら積み船運賃・関連ETFの上昇"})

    # ⑥ 為替バイアス（最優先フィルター ─ 最後に評価）
    # 円高進行: 輸出系セクターに逆風
    if jpyx <= -THRESHOLD_FX:
        # 他のルールで追い風判定されていても、円高なら上書き
        tailwinds = [t for t in tailwinds if t["sector"] not in ("輸送用機器", "ゴム製品")]
        headwinds = [h for h in headwinds if h["sector"] not in ("輸送用機器", "ゴム製品")]
        headwinds.append({"sector": "輸送用機器", "reason": "急激な円高進行による為替差損警戒"})
        headwinds.append({"sector": "ゴム製品", "reason": "急激な円高進行による為替差損警戒"})
    # 円安進行: 輸出系セクターに追い風
    elif jpyx >= THRESHOLD_FX:
        tailwinds = [t for t in tailwinds if t["sector"] != "輸送用機器"]
        headwinds = [h for h in headwinds if h["sector"] != "輸送用機器"]
        tailwinds.append({"sector": "輸送用機器", "reason": "円安進行による輸出採算改善期待"})

    # 重複排除（同一セクターが複数ルールでヒットした場合）
    seen_tw = set()
    unique_tailwinds = []
    for t in tailwinds:
        if t["sector"] not in seen_tw:
            seen_tw.add(t["sector"])
            unique_tailwinds.append(t)

    seen_hw = set()
    unique_headwinds = []
    for h in headwinds:
        if h["sector"] not in seen_hw:
            seen_hw.add(h["sector"])
            unique_headwinds.append(h)

    return unique_tailwinds, unique_headwinds
