# -*- coding: utf-8 -*-
"""
Gemini AI 深層分析モジュール
- gemini-2.0-flash によるセクターローテーション分析
- APIキー未設定・エラー時のフォールバック（定量サマリー）
"""

import os
import pandas as pd
from dotenv import load_dotenv

load_dotenv()


def _get_api_key() -> str | None:
    """Gemini APIキーを取得する（環境変数 or Streamlit Secrets）"""
    # 環境変数から取得
    key = os.getenv("GEMINI_API_KEY")
    if key and key != "your_gemini_api_key_here":
        return key

    # Streamlit Secrets から取得（クラウドデプロイ時）
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass

    return None


def _build_prompt(sector_summary: pd.DataFrame, oversold_stocks: pd.DataFrame,
                  volume_surge_stocks: pd.DataFrame, news_text: str, market_overview: dict) -> str:
    """AI分析用のプロンプトを構築する"""

    # セクター騰落率テキスト
    sector_text = "【全33業種のセクター別データ】\n"
    if not sector_summary.empty:
        for _, row in sector_summary.iterrows():
            avg_rsi = row.get('avg_rsi', 0) if pd.notna(row.get('avg_rsi')) else 0
            avg_vr = row.get('avg_volume_ratio', 0) if pd.notna(row.get('avg_volume_ratio')) else 0
            avg_pct = row.get('avg_percent_change', 0) if pd.notna(row.get('avg_percent_change')) else 0
            trading_val = row.get('trading_value', 0) if pd.notna(row.get('trading_value')) else 0
            stock_count = row.get('stock_count', 0)

            sector_text += (
                f"- {row['sector']}: "
                f"前日比={avg_pct:+.2f}%, "
                f"平均出来高倍率={avg_vr:.2f}x, "
                f"売買代金={trading_val:,.0f}, "
                f"平均RSI={avg_rsi:.1f}, "
                f"銘柄数={stock_count}\n"
            )
    else:
        sector_text += "データなし\n"

    # 売られすぎ銘柄テキスト
    oversold_text = "\n【RSI 30以下の売られすぎ銘柄】\n"
    if not oversold_stocks.empty:
        for _, row in oversold_stocks.head(20).iterrows():
            oversold_text += f"- {row['ticker']} ({row.get('name', '')}): RSI={row.get('rsi', 'N/A'):.1f}, セクター={row.get('sector', '')}\n"
    else:
        oversold_text += "該当なし\n"

    # 出来高急増テキスト
    volume_text = "\n【出来高急増銘柄（2倍以上）】\n"
    if not volume_surge_stocks.empty:
        for _, row in volume_surge_stocks.head(20).iterrows():
            volume_text += f"- {row['ticker']} ({row.get('name', '')}): 出来高倍率={row.get('volume_ratio', 'N/A'):.2f}x, セクター={row.get('sector', '')}\n"
    else:
        volume_text += "該当なし\n"

    # --- マクロ指標テキスト ---
    macro_text = "【主要マクロ指標（現在値・前日比）】\n"
    if market_overview:
        for key, data in market_overview.items():
            name = data.get("name", key)
            val = data.get("price", 0)
            chg = data.get("change_pct", 0)
            macro_text += f"- {name}: {val:,.2f} ({chg:+.2f}%)\n"
    else:
        macro_text += "データなし\n"

    # --- ▼ 最新の「辛口ストラテジスト」指示 ▼ ---
    prompt = f"""
あなたは、ウォール街と兜町で20年以上の経験を持つ「辛口かつ論理的な株式ストラテジスト」です。
提供された「定量データ（株価）」と「最新ニュース」を深く統合し、市場の背後にあるストーリー（ナラティブ）を解き明かしてください。

【タスクの最優先事項】
単なる「値動きの実況（〜が上がりました）」は不要です。「なぜ動いたのか？」という**背景要因（ニュース、決算、要人発言、地政学リスク）**を特定し、論理的に説明してください。

【入力データ】
1. マクロ環境ダッシュボード（日経先物や米国指数を含む）:
{macro_text}

2. セクター分析データ（定量）:
{sector_text}

2. 注目銘柄データ（売られすぎ/出来高急増）:
{oversold_text}
{volume_text}

3. 最新の市況ニュース・ヘッドライン（情報源）:
{news_text}

【出力フォーマットと指示】
以下の構成で、HTML形式（Markdown）で出力してください。です・ます調ですが、プロらしく断定的なトーンで書いてください。

## 1. 📰 マーケット・ナラティブ（深層分析）
* **市場のテーマ:** 現在、市場を支配しているメインテーマは何か？（例：「AIバブルの警戒感」「日銀の利上げ観測」など、ニュースから具体的な**固有名詞**を出して断定せよ）。また、入力された「マクロ環境ダッシュボード」の値（日経先物や米国株など）から、現在の地合いや明日の日本株の寄り付きに向けたバイアス（ギャップアップ警戒など）を読み解いて組み込め。
* **センチメント:** 投資家心理は「楽観」か「恐怖」か？それはどのニュース（例：アンソロピックの報道、米雇用統計など）に起因するか？
* **ニュースとの結合:** 上記の定量データで特異な動きをしているセクターについて、ニュース記事内の出来事と因果関係を紐づけて解説せよ。

## 2. 🔄 セクターローテーションの現状
* **資金の流れ:** どのセクターからどのセクターへ資金が移動しているか？（例：ハイテクからバリューへの逃避、など）
* **主役セクターの背景:** 最も強いセクターはなぜ買われているのか？（「原油高の恩恵」「半導体規制の影響」など具体的に）

## 3. 📉 逆張り・リバウンド狙いの戦略
* **売られすぎの正体:** リストアップされた「売られすぎ銘柄」は、単なる調整か？それとも悪材料が出た「落ちるナイフ」か？ニュースと照らし合わせて判断せよ。
* **注目銘柄:** 特にリバウンドが期待できそうな銘柄を1つ挙げ、その定量的・定性的な根拠を述べよ。

## 4. 🌤️ 相場天気予報コメント
以下の形式で、**必ず1行だけ**出力せよ（見出しやラベルは不要、コメント本文のみ）。
[WEATHER_COMMENT] ここにコメントを記載

このコメントは、ダッシュボードの天気予報パネルに表示される「解説文」の一部として使われる。
以下のルールに従って書くこと：
* 現在のニュース・材料と、日経先物やマクロ指標の動きを照らし合わせ、**この動きが「構造的（ファンダメンタルズに裏付けられた）」なのか、「一時的な連れ高/連れ安」なのか**を1〜2文で端的に判定して書け。
* 例（構造的な場合）：「米中関係の改善報道を受けた買いが入っており、半導体を中心に実需の買いが期待できます。」
* 例（一時的な場合）：「目立った国内材料はなく、米国ハイテク株の上昇に引きずられた連れ高の可能性があります。寄り付き後の値動きに注意が必要です。」
* 例（悲観的な場合）：「地政学リスクの高まりを嫌気した売りが優勢ですが、決算シーズンを控えた押し目買いも入りやすい水準です。」

【制約事項】
* 「変動しました」という曖昧な表現は禁止。「暴落」「急騰」「底堅い」など強い言葉を使うこと。
* ニュースがない場合は「特段の材料は見当たらないが、需給要因と思われる」と正直に書くこと。
* [WEATHER_COMMENT]の行は**必ず出力**すること。
"""

    return prompt


def _execute_gemini_call(prompt: str, api_key: str) -> str:
    """
    Gemini REST APIを直接呼び出す（grpcio不要のrequests使用）
    ARM64環境やビルド環境でも動作するようにgrpc依存なしで実装。
    429エラー時は120秒待機後に1回リトライする。
    """
    import requests as _req
    import json
    import time as _time

    models_to_try = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]
    base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    max_429_retries = 1  # 429エラー時の最大リトライ回数
    retry_429_count = 0

    last_error = None
    while True:
        for model_name in models_to_try:
            url = f"{base_url}/{model_name}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 8000}
            }
            try:
                resp = _req.post(url, json=payload, timeout=120)
                if resp.status_code == 429:
                    last_error = (
                        "APIの利用制限（429: Quota Exceeded）に達しました。\n\n"
                        "Google AI Studioの設定から「従量課金（Pay-as-you-go）」を有効にしてください。"
                    )
                    # 429はリトライ可能 → ループを抜けてリトライ判定へ
                    break
                if resp.status_code == 404:
                    # このモデルが存在しない場合は次を試す
                    last_error = f"Model {model_name} not found (404)"
                    continue
                resp.raise_for_status()
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                if text:
                    return text
            except Exception as e:
                last_error = str(e)
                continue
        else:
            # forループが正常終了（breakせず） = 429以外のエラーで全モデル失敗 → 諦める
            break

        # 429で抜けてきた場合のリトライ判定
        if retry_429_count < max_429_retries:
            retry_429_count += 1
            print(f"⏳ Gemini API 429エラー: {120}秒待機後にリトライします ({retry_429_count}/{max_429_retries})...")
            _time.sleep(120)
            continue
        else:
            break

    raise Exception(f"Gemini APIの呼び出しに失敗しました。詳細: {last_error}")


def analyze_with_gemini(sector_summary: pd.DataFrame, oversold_stocks: pd.DataFrame,
                        volume_surge_stocks: pd.DataFrame, news_text: str, market_overview: dict = None) -> str:
    """
    Gemini APIを使用してセクターローテーション分析を実行する
    APIキー未設定やエラー時はフォールバックサマリーを返す
    """
    api_key = _get_api_key()

    if not api_key:
        return _generate_fallback_summary(sector_summary, oversold_stocks, volume_surge_stocks)

    try:
        prompt = _build_prompt(sector_summary, oversold_stocks, volume_surge_stocks, news_text, market_overview)
        return _execute_gemini_call(prompt, api_key)

    except Exception as e:
        error_msg = f"⚠️ Gemini API エラー: {str(e)}\n\n"
        error_msg += _generate_fallback_summary(sector_summary, oversold_stocks, volume_surge_stocks)
        return error_msg


def _generate_fallback_summary(sector_summary: pd.DataFrame, oversold_stocks: pd.DataFrame,
                                volume_surge_stocks: pd.DataFrame) -> str:
    """
    AIなしの定量データに基づく簡易サマリーを生成する（フォールバック）
    """
    lines = ["## 📊 定量分析サマリー（AIなし）\n"]
    lines.append("*Gemini APIが利用できないため、定量データのみに基づく分析です。*\n")

    # 出来高急増セクター
    if not sector_summary.empty:
        lines.append("### 🔥 出来高が活発なセクター（上位5）")
        top_sectors = sector_summary.nlargest(5, "avg_volume_ratio")
        for _, row in top_sectors.iterrows():
            lines.append(
                f"- **{row['sector']}**: 平均出来高倍率 {row.get('avg_volume_ratio', 0):.2f}x, "
                f"平均RSI {row.get('avg_rsi', 0):.1f}"
            )
        lines.append("")

    # RSI低セクター（逆張り候補）
    if not sector_summary.empty:
        lines.append("### 📉 RSIが低いセクター（逆張り候補、上位5）")
        low_rsi = sector_summary.nsmallest(5, "avg_rsi")
        for _, row in low_rsi.iterrows():
            lines.append(
                f"- **{row['sector']}**: 平均RSI {row.get('avg_rsi', 0):.1f}, "
                f"平均出来高倍率 {row.get('avg_volume_ratio', 0):.2f}x"
            )
        lines.append("")

    # 売られすぎ銘柄
    if not oversold_stocks.empty:
        lines.append("### ⚡ 売られすぎ銘柄（RSI ≤ 30）")
        for _, row in oversold_stocks.head(10).iterrows():
            lines.append(
                f"- **{row['ticker']}** ({row.get('name', '')}): "
                f"RSI={row.get('rsi', 0):.1f}, セクター={row.get('sector', '')}"
            )
        lines.append("")

    # 出来高急増銘柄
    if not volume_surge_stocks.empty:
        lines.append("### 📈 出来高急増銘柄（上位10）")
        for _, row in volume_surge_stocks.head(10).iterrows():
            lines.append(
                f"- **{row['ticker']}** ({row.get('name', '')}): "
                f"出来高倍率={row.get('volume_ratio', 0):.2f}x, セクター={row.get('sector', '')}"
            )
        lines.append("")

    if len(lines) <= 2:
        lines.append("データが不足しているため、分析を実行できません。\n「データを最新化」ボタンを押してデータを取得してください。")

    return "\n".join(lines)


def get_shared_ai_insight(date_str: str, db_version: float):
    """
    ダッシュボードとAIインサイトページで共有するための分析実行・キャッシュ関数
    db_version に db_manager.get_db_last_modified() を渡すことで、
    DBが更新された（＝データを最新化した）タイミングでキャッシュが破棄・再実行される
    """
    import streamlit as st
    from modules.db_manager import get_sector_summary, get_oversold_stocks, get_volume_surge_stocks
    from modules.news_fetcher import fetch_news_summary
    from datetime import datetime, timezone, timedelta

    @st.cache_data(show_spinner="🤖 Gemini AIが深層分析を実行中...（30秒ほどかかる場合があります）")
    def _run_analysis(d_str: str, v: float):
        sector_summary = get_sector_summary(d_str)
        oversold = get_oversold_stocks(d_str)
        volume_surge = get_volume_surge_stocks(d_str)
        news_text = fetch_news_summary(max_articles=15)
        
        # マクロ指標の取得（AI分析用）
        from modules.market_overview import fetch_market_overview
        market_overview = fetch_market_overview()
        
        result = analyze_with_gemini(sector_summary, oversold, volume_surge, news_text, market_overview)
        
        # AIの返答から天気予報コメントをパースする
        weather_comment = ""
        if result and "[WEATHER_COMMENT]" in result:
            for line in result.split("\n"):
                if "[WEATHER_COMMENT]" in line:
                    weather_comment = line.replace("[WEATHER_COMMENT]", "").strip()
                    break
            # 本文からマーカー行を除去（AIインサイト表示時に邪魔にならないよう）
            result = "\n".join(l for l in result.split("\n") if "[WEATHER_COMMENT]" not in l)
        
        jst = timezone(timedelta(hours=9))
        return result, datetime.now(jst).strftime("%H:%M"), weather_comment
        
    return _run_analysis(date_str, db_version)

def clear_shared_ai_insight():
    """
    共有AIインサイトのキャッシュをクリアする
    """
    import streamlit as st
    # get_shared_ai_insight 内の _run_analysis のキャッシュクリア
    st.cache_data.clear()

# ------------------------------------------------------------------------------------------------
# 以下、個別チャートの参考ちゃんAPI制限のため一時削除
# ------------------------------------------------------------------------------------------------
