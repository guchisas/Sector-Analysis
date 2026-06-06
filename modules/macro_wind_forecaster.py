# -*- coding: utf-8 -*-
"""
セクター風向き予想モジュール (Macro Wind Forecaster) - AIネイティブ統合版

== アーキテクチャ ==
STEP1: 定量ファクト収集 + システム1次判定（地合い・資金移動・カレンダー例外）
STEP2: Gemini AIによる2次判定（定量×定性の統合 → 構造化JSON出力）
フォールバック: AI不使用時はしきい値ベースのルールエンジンで代替

== 出力 ==
{
  "playbook": "AI生成の統合シナリオ（150文字）",
  "tailwind_sectors": [{"sector": "...", "sub_focus": "...", "reason": "...", "evidence_ticker": "..."}],
  "headwind_sectors": [...],
  "evidence": { ... ファクトバッジ用データ ... },
  "warnings": ["SQ日警告", ...],
  "is_us_holiday": False,
  "analyzed_at": "HH:MM"
}
"""

import yfinance as yf
import streamlit as st
import json
import re
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta

from utils.constants import (
    MACRO_TICKERS, NEWS_SPAM_KEYWORDS,
    get_calendar_warnings, is_us_market_holiday_yesterday, is_earnings_season
)

# =====================================================================
# しきい値定義（フォールバック用 — 既存互換）
# =====================================================================
THRESHOLD_SEMI = 1.5       # 半導体 (SMH) しきい値 (%)
THRESHOLD_SAAS = 1.5       # SaaS/クラウド (IGV) しきい値 (%)
THRESHOLD_RESOURCE = 1.5   # 資源 (XME) しきい値 (%)
THRESHOLD_FX = 0.5         # 為替 (JPY=X) しきい値 (%)


# =====================================================================
# A. データ取得レイヤー
# =====================================================================
@st.cache_data(ttl=3600, show_spinner="🌍 海外マクロデータを取得中...")
def fetch_macro_data() -> Dict[str, Optional[float]]:
    """
    MACRO_TICKERSに定義された全ティッカーの前日比騰落率(%)を取得する。
    リアルタイム対象(JPY=X, NIY=F)は現在値も併せて取得する。
    
    Returns:
        dict: {
            "changes": {"^GSPC": 0.35, "SMH": 1.8, ...},  // 前日比%
            "prices":  {"JPY=X": 149.50, "NIY=F": 38500, ...},  // 現在値
            "raw":     {"^GSPC": {"price": 5100, "prev": 5082}, ...}  // 詳細
        }
    """
    changes = {}
    prices = {}
    raw = {}

    # 全カテゴリからティッカーを収集
    all_tickers = {}
    for category in MACRO_TICKERS.values():
        all_tickers.update(category)

    for ticker_symbol, label in all_tickers.items():
        try:
            ticker = yf.Ticker(ticker_symbol)
            df = ticker.history(period="5d", interval="1d")

            if df.empty or "Close" not in df.columns or len(df) < 2:
                changes[ticker_symbol] = None
                continue

            close = df["Close"]
            latest = float(close.iloc[-1])
            prev = float(close.iloc[-2])

            if prev != 0:
                change_pct = ((latest - prev) / prev) * 100
            else:
                change_pct = 0.0

            changes[ticker_symbol] = round(change_pct, 3)
            raw[ticker_symbol] = {"price": latest, "prev": prev, "change_pct": round(change_pct, 3)}

            # リアルタイム対象は現在値も保存
            if ticker_symbol in MACRO_TICKERS.get("realtime", {}):
                # ticker.infoからリアルタイム価格を試行
                try:
                    info = ticker.info
                    rt_price = info.get("regularMarketPrice") or info.get("bid") or latest
                    prices[ticker_symbol] = round(float(rt_price), 2)
                except Exception:
                    prices[ticker_symbol] = round(latest, 2)
            else:
                prices[ticker_symbol] = round(latest, 2)

        except Exception as e:
            print(f"⚠️ {ticker_symbol} ({label}) の取得に失敗: {e}")
            changes[ticker_symbol] = None

    return {"changes": changes, "prices": prices, "raw": raw}


def _filter_news_spam(articles: List[Dict]) -> List[Dict]:
    """ニュースからPR・スパム記事をフィルタリングする"""
    filtered = []
    for article in articles:
        title = article.get("title", "")
        source = article.get("source", "")
        # タイトルまたはソースにスパムキーワードが含まれるか
        is_spam = any(kw in title for kw in NEWS_SPAM_KEYWORDS)
        if not is_spam:
            filtered.append(article)
    return filtered


def fetch_news_for_macro(max_articles: int = 3) -> List[Dict]:
    """マクロ分析用にフィルタリング済みのトップニュースを取得する"""
    try:
        from modules.news_fetcher import fetch_news
        raw_news = fetch_news(hours=24)
        clean_news = _filter_news_spam(raw_news)
        return clean_news[:max_articles]
    except Exception as e:
        print(f"⚠️ マクロ用ニュース取得失敗: {e}")
        return []


# =====================================================================
# B. STEP1: システム1次判定エンジン
# =====================================================================
def run_step1_analysis(macro_data: Dict) -> Dict[str, Any]:
    """
    定量データからファクトを整理し、1次判定を行う。
    
    Returns:
        dict: {
            "macro_regime": "growth" | "value" | "recession_warning",
            "macro_regime_label": "グロース優位" | "バリュー優位" | "リセッション警戒",
            "yield_spread": float (長短金利差),
            "strongest": {"ticker": "SMH", "label": "半導体ETF", "change": 2.5},
            "weakest":  {"ticker": "XLF", "label": "金融ETF", "change": -1.8},
            "fx_bias":  "yen_weak" | "yen_strong" | "neutral",
            "fx_price": 149.50,
            "futures_price": 38500,
            "futures_gap": 0.8,  (%)
            "oil_change": -2.1,
            "calendar_warnings": ["..."],
            "is_us_holiday": False,
            "is_earnings_season": False,
        }
    """
    changes = macro_data.get("changes", {})
    prices = macro_data.get("prices", {})
    raw = macro_data.get("raw", {})

    # --- 米国休場判定 ---
    sp500_change = changes.get("^GSPC")
    is_holiday = sp500_change is None
    
    if is_holiday:
        return {
            "macro_regime": "unknown",
            "macro_regime_label": "データなし",
            "yield_spread": 0,
            "strongest": None,
            "weakest": None,
            "fx_bias": "neutral",
            "fx_price": prices.get("JPY=X", 0),
            "futures_price": prices.get("NIY=F", 0),
            "futures_gap": 0,
            "oil_change": 0,
            "calendar_warnings": ["🔇 米国市場が休場のため、前日のマクロデータはありません。"],
            "is_us_holiday": True,
            "is_earnings_season": is_earnings_season(),
        }

    # --- マクロ地合い判定 ---
    dow_change = changes.get("^DJI", 0) or 0
    nasdaq_change = changes.get("^IXIC", 0) or 0
    tnx_change = changes.get("^TNX", 0) or 0
    irx_change = changes.get("^IRX", 0) or 0

    # ダウvsNASDAQスプレッド（正=グロース優位、負=バリュー優位）
    growth_value_spread = nasdaq_change - dow_change

    # 長短金利差（10年-13週）の水準
    tnx_price = prices.get("^TNX", 0)
    irx_price = prices.get("^IRX", 0)
    yield_spread = round(tnx_price - irx_price, 3) if tnx_price and irx_price else 0

    # 地合い判定
    if yield_spread < 0 and sp500_change < -0.5:
        macro_regime = "recession_warning"
        macro_regime_label = "🔴 リセッション警戒"
    elif growth_value_spread > 0.5:
        macro_regime = "growth"
        macro_regime_label = "🟢 グロース優位"
    elif growth_value_spread < -0.5:
        macro_regime = "value"
        macro_regime_label = "🟡 バリュー優位"
    else:
        macro_regime = "neutral"
        macro_regime_label = "⚪ 方向感なし"

    # --- サブセクターETFの最強/最弱抽出 ---
    etf_tickers = MACRO_TICKERS.get("sector_etfs", {})
    megacap_tickers = MACRO_TICKERS.get("megacaps", {})
    all_sub = {**etf_tickers, **megacap_tickers}
    
    sub_changes = {}
    for t, label in all_sub.items():
        c = changes.get(t)
        if c is not None:
            sub_changes[t] = {"label": label, "change": c}

    strongest = None
    weakest = None
    if sub_changes:
        strongest_key = max(sub_changes, key=lambda k: sub_changes[k]["change"])
        weakest_key = min(sub_changes, key=lambda k: sub_changes[k]["change"])
        strongest = {"ticker": strongest_key, **sub_changes[strongest_key]}
        weakest = {"ticker": weakest_key, **sub_changes[weakest_key]}

    # --- 為替バイアス ---
    fx_change = changes.get("JPY=X", 0) or 0
    fx_price = prices.get("JPY=X", 0)
    if fx_change >= THRESHOLD_FX:
        fx_bias = "yen_weak"  # 円安（ドル高）
    elif fx_change <= -THRESHOLD_FX:
        fx_bias = "yen_strong"  # 円高（ドル安）
    else:
        fx_bias = "neutral"

    # --- 先物ギャップ ---
    futures_price = prices.get("NIY=F", 0)

    # --- 原油 ---
    oil_change = changes.get("CL=F", 0) or 0

    # --- カレンダー警告 ---
    calendar_warnings = get_calendar_warnings()

    return {
        "macro_regime": macro_regime,
        "macro_regime_label": macro_regime_label,
        "yield_spread": yield_spread,
        "strongest": strongest,
        "weakest": weakest,
        "fx_bias": fx_bias,
        "fx_price": fx_price,
        "futures_price": futures_price,
        "futures_gap": 0,  # ダッシュボード側で日経終値と比較して算出
        "oil_change": round(oil_change, 2),
        "calendar_warnings": calendar_warnings,
        "is_us_holiday": False,
        "is_earnings_season": is_earnings_season(),
    }


# =====================================================================
# C. STEP2: Gemini AIによる2次判定（構造化JSON出力）
# =====================================================================
def _build_macro_ai_prompt(step1: Dict, macro_data: Dict, news_headlines: List[Dict]) -> str:
    """マクロ風向き予想用のAIプロンプトを構築する"""
    changes = macro_data.get("changes", {})
    prices = macro_data.get("prices", {})

    # --- 定量ファクトの整理 ---
    quant_lines = []
    quant_lines.append("【主要指数（前日比%）】")
    for t, label in MACRO_TICKERS.get("indices", {}).items():
        c = changes.get(t)
        quant_lines.append(f"  {label}: {c:+.2f}%" if c is not None else f"  {label}: N/A")

    quant_lines.append("\n【金利】")
    for t, label in MACRO_TICKERS.get("rates", {}).items():
        p = prices.get(t, 0)
        c = changes.get(t)
        quant_lines.append(f"  {label}: {p:.3f}% (前日比 {c:+.3f}%)" if c is not None else f"  {label}: N/A")
    quant_lines.append(f"  長短金利差(10Y-13W): {step1.get('yield_spread', 0):.3f}%")

    quant_lines.append("\n【コモディティ】")
    for t, label in MACRO_TICKERS.get("commodities", {}).items():
        p = prices.get(t, 0)
        c = changes.get(t)
        quant_lines.append(f"  {label}: ${p:,.2f} ({c:+.2f}%)" if c is not None else f"  {label}: N/A")

    quant_lines.append("\n【サブセクターETF（前日比%）】")
    for t, label in MACRO_TICKERS.get("sector_etfs", {}).items():
        c = changes.get(t)
        quant_lines.append(f"  {t} ({label}): {c:+.2f}%" if c is not None else f"  {t} ({label}): N/A")

    quant_lines.append("\n【メガキャップ（前日比%）】")
    for t, label in MACRO_TICKERS.get("megacaps", {}).items():
        c = changes.get(t)
        quant_lines.append(f"  {t} ({label}): {c:+.2f}%" if c is not None else f"  {t} ({label}): N/A")

    quant_lines.append(f"\n【リアルタイム為替・先物（現在値）】")
    quant_lines.append(f"  ドル円: ¥{step1.get('fx_price', 0):,.2f}")
    quant_lines.append(f"  CME日経先物: ¥{step1.get('futures_price', 0):,.0f}")

    quant_text = "\n".join(quant_lines)

    # --- システム1次判定結果 ---
    regime_text = f"マクロ地合い判定: {step1.get('macro_regime_label', 'N/A')}"
    strongest = step1.get("strongest")
    weakest = step1.get("weakest")
    if strongest:
        regime_text += f"\n最強セクター: {strongest['ticker']} ({strongest['label']}) {strongest['change']:+.2f}%"
    if weakest:
        regime_text += f"\n最弱セクター: {weakest['ticker']} ({weakest['label']}) {weakest['change']:+.2f}%"

    # --- カレンダー警告 ---
    cal_text = ""
    warnings = step1.get("calendar_warnings", [])
    if warnings:
        cal_text = "\n【カレンダー要因】\n" + "\n".join(warnings)
        cal_text += "\n※ 上記のカレンダー要因がある場合、playbook内で必ずその影響に言及すること。"

    # --- ニュースヘッドライン ---
    news_text = "\n【前日の米国市場に関する主要ニュース】\n"
    if news_headlines:
        for i, article in enumerate(news_headlines, 1):
            title = article.get("title", "")
            summary = article.get("summary", "")[:80]
            news_text += f"  {i}. {title}\n"
            if summary:
                news_text += f"     概要: {summary}\n"
    else:
        news_text += "  特筆すべきニュースなし\n"

    # --- プロンプト本体 ---
    prompt = f"""あなたは、ウォール街で20年以上の経験を持つ機関投資家ストラテジストです。
提示された「定量データ」と「ニュース」のみを統合し、以下の厳密なJSONフォーマットで回答してください。

【タスク制限】
- 推測による未来の株価予知は絶対に行わないこと
- 提示された事実（数値・ニュース・カレンダー要因）のみに基づいて判断すること
- 出力は純粋なJSONのみ。マークダウンのコードブロック記法（```json）は使用しないこと

【入力データ】
{quant_text}

【システム1次判定】
{regime_text}
{cal_text}
{news_text}

【出力フォーマット（厳密にこのJSON構造で返却せよ）】
{{
  "playbook": "昨晩の海外機関の資金移動の意図と、本日の日本市場への論理的な波及シナリオ。150文字以内。カレンダー要因がある場合はその警告を含めること。",
  "tailwind_sectors": [
    {{
      "sector": "東証33業種の正式名称",
      "sub_focus": "セクター内のサブ領域（例：半導体関連、メガバンクなど）",
      "reason": "追い風の根拠を簡潔に（40文字以内）",
      "evidence_ticker": "根拠となる米国ティッカー（例：SMH）"
    }}
  ],
  "headwind_sectors": [
    {{
      "sector": "東証33業種の正式名称",
      "sub_focus": "セクター内のサブ領域",
      "reason": "逆風の根拠を簡潔に（40文字以内）",
      "evidence_ticker": "根拠となる米国ティッカー"
    }}
  ]
}}

【制約】
- tailwind_sectorsは最大3つ。該当なしなら空配列。
- headwind_sectorsは最大3つ。該当なしなら空配列。
- sectorは東証33業種の正式名称から選ぶこと（電気機器、銀行業、情報・通信業、など）。
- evidence_tickerは入力データに含まれるティッカーシンボルから選ぶこと。
- 日本語で回答すること。"""

    return prompt


def run_step2_ai_analysis(step1: Dict, macro_data: Dict, news_headlines: List[Dict]) -> Optional[Dict]:
    """
    Gemini AIに定量×定性データを渡し、構造化JSONで機関の意図と波及シナリオを抽出する。
    
    Returns:
        dict or None: AIの解析結果。失敗時はNone。
    """
    from modules.ai_analyzer import _get_api_key, _execute_gemini_call

    api_key = _get_api_key()
    if not api_key:
        return None

    try:
        prompt = _build_macro_ai_prompt(step1, macro_data, news_headlines)
        raw_response = _execute_gemini_call(prompt, api_key)

        # --- JSON抽出（堅牢化） ---
        # AIがマークダウンのコードブロックで囲んだ場合に対応
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw_response)
        if json_match:
            json_str = json_match.group(1)
        else:
            # コードブロックなしの場合、最初の { から最後の } までを抽出
            brace_start = raw_response.find('{')
            brace_end = raw_response.rfind('}')
            if brace_start != -1 and brace_end != -1:
                json_str = raw_response[brace_start:brace_end + 1]
            else:
                print(f"⚠️ AI応答からJSONを抽出できません: {raw_response[:200]}")
                return None

        result = json.loads(json_str)

        # 必須キーの検証
        if "playbook" not in result:
            return None

        # tailwind/headwindがなければ空リスト
        result.setdefault("tailwind_sectors", [])
        result.setdefault("headwind_sectors", [])

        # 最大3つに制限
        result["tailwind_sectors"] = result["tailwind_sectors"][:3]
        result["headwind_sectors"] = result["headwind_sectors"][:3]

        return result

    except json.JSONDecodeError as e:
        print(f"⚠️ AI応答のJSONパースに失敗: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Gemini API呼び出し失敗: {e}")
        return None


# =====================================================================
# D. フォールバック: しきい値ベースのルール判定（AI不使用時）
# =====================================================================
def _generate_fallback_result(step1: Dict, macro_data: Dict) -> Dict:
    """AI不使用時のフォールバック結果を生成する"""
    changes = macro_data.get("changes", {})

    def _get(key: str) -> float:
        v = changes.get(key)
        return v if v is not None else 0.0

    smh = _get("SMH")
    igv = _get("IGV")
    xlf = _get("XLF")
    tnx = _get("^TNX")
    xme = _get("XME")
    jpyx = _get("JPY=X")

    tailwinds = []
    headwinds = []

    # ① 半導体・ハイテク連動
    if smh >= THRESHOLD_SEMI:
        tailwinds.append({"sector": "電気機器", "sub_focus": "半導体関連", "reason": "半導体ETF(SMH)の上昇で関連銘柄に追い風", "evidence_ticker": "SMH"})
        tailwinds.append({"sector": "精密機器", "sub_focus": "半導体製造装置", "reason": "半導体増産→製造装置の受注増加期待", "evidence_ticker": "SMH"})
    elif smh <= -THRESHOLD_SEMI:
        headwinds.append({"sector": "電気機器", "sub_focus": "半導体関連", "reason": "半導体需要の鈍化懸念で売り優勢", "evidence_ticker": "SMH"})
        headwinds.append({"sector": "精密機器", "sub_focus": "半導体製造装置", "reason": "半導体の設備投資サイクル減速懸念", "evidence_ticker": "SMH"})

    # ② ソフトウェア・グロース連動
    if igv >= THRESHOLD_SAAS:
        tailwinds.append({"sector": "情報・通信業", "sub_focus": "SaaS・クラウド関連", "reason": "DX投資拡大期待でクラウド関連に資金流入", "evidence_ticker": "IGV"})
    elif igv <= -THRESHOLD_SAAS:
        headwinds.append({"sector": "情報・通信業", "sub_focus": "SaaS・クラウド関連", "reason": "金利高止まりでグロース株から資金流出", "evidence_ticker": "IGV"})

    # ③ 金融・金利連動
    if xlf > 0 and tnx > 0:
        tailwinds.append({"sector": "銀行業", "sub_focus": "メガバンク・地銀", "reason": "長期金利上昇で利ざや拡大期待", "evidence_ticker": "XLF"})
    elif xlf < 0 and tnx < 0:
        headwinds.append({"sector": "銀行業", "sub_focus": "メガバンク・地銀", "reason": "金利低下で利ざや縮小懸念", "evidence_ticker": "XLF"})

    # ④ 資源・市況連動
    if xme >= THRESHOLD_RESOURCE:
        tailwinds.append({"sector": "非鉄金属", "sub_focus": "銅・アルミ製錬", "reason": "資源価格上昇で製錬マージン改善", "evidence_ticker": "XME"})

    # ⑤ 為替バイアス
    if jpyx >= THRESHOLD_FX:
        tailwinds.append({"sector": "輸送用機器", "sub_focus": "自動車・完成車メーカー", "reason": "円安で輸出採算改善", "evidence_ticker": "JPY=X"})
    elif jpyx <= -THRESHOLD_FX:
        headwinds.append({"sector": "輸送用機器", "sub_focus": "自動車・完成車メーカー", "reason": "円高で為替差損リスク拡大", "evidence_ticker": "JPY=X"})

    # 重複排除（最大3つ）
    seen_tw = set()
    unique_tw = []
    for t in tailwinds:
        if t["sector"] not in seen_tw and len(unique_tw) < 3:
            seen_tw.add(t["sector"])
            unique_tw.append(t)
    seen_hw = set()
    unique_hw = []
    for h in headwinds:
        if h["sector"] not in seen_hw and len(unique_hw) < 3:
            seen_hw.add(h["sector"])
            unique_hw.append(h)

    # フォールバック用playbook生成
    regime = step1.get("macro_regime_label", "")
    strongest = step1.get("strongest")
    weakest = step1.get("weakest")
    parts = [f"昨晩の米国市場は{regime}の展開。"]
    if strongest:
        parts.append(f"最も強かったのは{strongest['label']}({strongest['change']:+.1f}%)")
    if weakest:
        parts.append(f"、最も弱かったのは{weakest['label']}({weakest['change']:+.1f}%)")
    parts.append("。")

    cal_warnings = step1.get("calendar_warnings", [])
    if cal_warnings:
        parts.append(cal_warnings[0].replace("⚠️ ", "").replace("📢 ", ""))

    playbook = "".join(parts)[:150]

    return {
        "playbook": playbook,
        "tailwind_sectors": unique_tw,
        "headwind_sectors": unique_hw,
    }


# =====================================================================
# E. 公開エントリーポイント（スロット制キャッシュ）
# =====================================================================
def get_macro_wind_forecast() -> Dict[str, Any]:
    """
    マクロ風向き予想のメインエントリーポイント。
    
    【コスト最適化 — スロット制】
    1日3スロット（JST 8:00 / 12:30 / 16:00）で区切り、
    各スロットの最初のアクセス時にのみAI+データ取得を1回実行。
    同じスロット内ではキャッシュを返す。
    """
    from modules.ai_analyzer import get_ai_slot
    slot_id = get_ai_slot()
    return _cached_macro_wind_forecast(slot_id)


@st.cache_data(show_spinner="🌍 海外機関プレイブック＆風向き予想を分析中...")
def _cached_macro_wind_forecast(slot_id: str) -> Dict[str, Any]:
    """スロットIDをキャッシュキーとして使用する内部関数"""
    jst = timezone(timedelta(hours=9))
    analyzed_at = datetime.now(jst).strftime("%H:%M")

    # --- データ取得 ---
    macro_data = fetch_macro_data()
    news_headlines = fetch_news_for_macro(max_articles=3)

    # --- STEP1: システム1次判定 ---
    step1 = run_step1_analysis(macro_data)

    # --- 米国休場チェック ---
    if step1.get("is_us_holiday"):
        return {
            "playbook": "米国市場が休場のため、前日のマクロデータはありません。本日は国内要因のみで相場が動きます。",
            "tailwind_sectors": [],
            "headwind_sectors": [],
            "evidence": step1,
            "warnings": step1.get("calendar_warnings", []),
            "is_us_holiday": True,
            "is_earnings_season": step1.get("is_earnings_season", False),
            "analyzed_at": analyzed_at,
        }

    # --- STEP2: AI 2次判定 ---
    ai_result = run_step2_ai_analysis(step1, macro_data, news_headlines)

    if ai_result:
        # AI成功 → AI結果を採用
        playbook = ai_result.get("playbook", "")
        tailwinds = ai_result.get("tailwind_sectors", [])
        headwinds = ai_result.get("headwind_sectors", [])
    else:
        # AIフォールバック → しきい値ルールベース
        fallback = _generate_fallback_result(step1, macro_data)
        playbook = fallback["playbook"]
        tailwinds = fallback["tailwind_sectors"]
        headwinds = fallback["headwind_sectors"]

    # --- カレンダー警告をplaybookに反映 ---
    warnings = step1.get("calendar_warnings", [])

    return {
        "playbook": playbook,
        "tailwind_sectors": tailwinds,
        "headwind_sectors": headwinds,
        "evidence": step1,
        "warnings": warnings,
        "is_us_holiday": False,
        "is_earnings_season": step1.get("is_earnings_season", False),
        "analyzed_at": analyzed_at,
    }


# =====================================================================
# 後方互換: 旧API（他のモジュールから参照されている場合）
# =====================================================================
def fetch_us_gear_data() -> Dict[str, Optional[float]]:
    """後方互換用: 旧fetch_us_gear_dataのラッパー"""
    data = fetch_macro_data()
    return data.get("changes", {})


def generate_wind_forecast(gear_data=None):
    """後方互換用: 旧generate_wind_forecastのラッパー"""
    result = get_macro_wind_forecast()
    tw = [{"sector": t["sector"], "sub_focus": t.get("sub_focus", ""), "reason": t.get("reason", "")} for t in result.get("tailwind_sectors", [])]
    hw = [{"sector": h["sector"], "sub_focus": h.get("sub_focus", ""), "reason": h.get("reason", "")} for h in result.get("headwind_sectors", [])]
    return tw, hw


def enrich_with_ai_insight(tailwinds, headwinds, ai_text):
    """後方互換用: 旧enrich_with_ai_insightのラッパー（何もせず返す）"""
    return tailwinds, headwinds
