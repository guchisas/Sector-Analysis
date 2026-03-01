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
                  volume_surge_stocks: pd.DataFrame, news_text: str) -> str:
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

    # --- ▼ 最新の「辛口ストラテジスト」指示 ▼ ---
    prompt = f"""
あなたは、ウォール街と兜町で20年以上の経験を持つ「辛口かつ論理的な株式ストラテジスト」です。
提供された「定量データ（株価）」と「最新ニュース」を深く統合し、市場の背後にあるストーリー（ナラティブ）を解き明かしてください。

【タスクの最優先事項】
単なる「値動きの実況（〜が上がりました）」は不要です。「なぜ動いたのか？」という**背景要因（ニュース、決算、要人発言、地政学リスク）**を特定し、論理的に説明してください。

【入力データ】
1. セクター分析データ（定量）:
{sector_text}

2. 注目銘柄データ（売られすぎ/出来高急増）:
{oversold_text}
{volume_text}

3. 最新の市況ニュース・ヘッドライン（情報源）:
{news_text}

【出力フォーマットと指示】
以下の構成で、HTML形式（Markdown）で出力してください。です・ます調ですが、プロらしく断定的なトーンで書いてください。

## 1. 📰 マーケット・ナラティブ（深層分析）
* **市場のテーマ:** 現在、市場を支配しているメインテーマは何か？（例：「AIバブルの警戒感」「日銀の利上げ観測」など、ニュースから具体的な**固有名詞**を出して断定せよ）
* **センチメント:** 投資家心理は「楽観」か「恐怖」か？それはどのニュース（例：アンソロピックの報道、米雇用統計など）に起因するか？
* **ニュースとの結合:** 上記の定量データで特異な動きをしているセクターについて、ニュース記事内の出来事と因果関係を紐づけて解説せよ。

## 2. 🔄 セクターローテーションの現状
* **資金の流れ:** どのセクターからどのセクターへ資金が移動しているか？（例：ハイテクからバリューへの逃避、など）
* **主役セクターの背景:** 最も強いセクターはなぜ買われているのか？（「原油高の恩恵」「半導体規制の影響」など具体的に）

## 3. 📉 逆張り・リバウンド狙いの戦略
* **売られすぎの正体:** リストアップされた「売られすぎ銘柄」は、単なる調整か？それとも悪材料が出た「落ちるナイフ」か？ニュースと照らし合わせて判断せよ。
* **注目銘柄:** 特にリバウンドが期待できそうな銘柄を1つ挙げ、その定量的・定性的な根拠を述べよ。

【制約事項】
* 「変動しました」という曖昧な表現は禁止。「暴落」「急騰」「底堅い」など強い言葉を使うこと。
* ニュースがない場合は「特段の材料は見当たらないが、需給要因と思われる」と正直に書くこと。
"""

    return prompt


def analyze_with_gemini(sector_summary: pd.DataFrame, oversold_stocks: pd.DataFrame,
                        volume_surge_stocks: pd.DataFrame, news_text: str) -> str:
    """
    Gemini APIを使用してセクターローテーション分析を実行する

    APIキー未設定やエラー時はフォールバックサマリーを返す
    """
    api_key = _get_api_key()

    if not api_key:
        return _generate_fallback_summary(sector_summary, oversold_stocks, volume_surge_stocks)

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        # 安定稼働する最新・安定版モデルのみ許可
        available_models = [
            m.name for m in genai.list_models()
            if "generateContent" in m.supported_generation_methods
        ]
        
        # 優先順位リスト（最新・安定動作が確認されているモデル名へ更新）
        preferred_models = [
            "models/gemini-2.0-flash",        # 最新の主力モデル
            "models/gemini-2.5-flash",        # 最新の高速版
            "models/gemini-1.5-flash",        # 旧モデルのフォールバック
            "models/gemini-pro"               # 完全なフォールバック
        ]
        
        selected_model = None
        # 優先リストの上から順に、使えるものがあるかチェック
        for p in preferred_models:
            if p in available_models:
                selected_model = p
                break
                
        # 優先順位のものが見つからなければ、利用可能な最初のモデル（2.0以外）を使用
        if not selected_model and available_models:
            selected_model = available_models[0]
            
        if not selected_model:
            raise Exception("有効なGemini生成モデルが見つかりません（無料枠制限の可能性）。")
            
        # パスプレフィックス "models/" を除去してモデル名を取得し、エラー耐性を高める
        model_name = selected_model.replace("models/", "")
        
        try:
            model = genai.GenerativeModel(selected_model) # 正式名称でトライ
        except Exception:
            model = genai.GenerativeModel(model_name) # ダメなら短い名前でトライ

        prompt = _build_prompt(sector_summary, oversold_stocks, volume_surge_stocks, news_text)

        response = model.generate_content(prompt)
        return response.text

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
        
        result = analyze_with_gemini(sector_summary, oversold, volume_surge, news_text)
        
        jst = timezone(timedelta(hours=9))
        return result, datetime.now(jst).strftime("%H:%M")
        
    return _run_analysis(date_str, db_version)

def clear_shared_ai_insight():
    """
    共有AIインサイトのキャッシュをクリアする
    """
    import streamlit as st
    # get_shared_ai_insight 内の _run_analysis のキャッシュクリア
    st.cache_data.clear()

def _build_swing_prompt(ticker: str, facts: dict) -> str:
    """参考ちゃん（スイングアナリスト）への制約付きプロンプトを構築する"""
    is_falling_knife = facts.get("is_falling_knife", False)
    is_breakout = facts.get("is_breakout", False)
    rr_ratio = facts.get("rr_ratio", 0.0)
    
    fact_text = f"""
【対象銘柄】{ticker}
【現在値】{facts.get('current_close', 0):,.1f} 円
【25SMA】{facts.get('sma25', 0):,.1f} 円
【75SMA】{facts.get('sma75', 0):,.1f} 円
【直近40日最高値 (Pivot)】{facts.get('pivot_40d', 0):,.1f} 円
【20日平均出来高】{facts.get('20d_avg_volume', 0):,.0f} 株
【直近出来高】{facts.get('current_volume', 0):,.0f} 株

--- 判定フラグ ---
・落ちるナイフ状態（現在値<25SMA<75SMA）: {is_falling_knife}
・ブレイクアウト状態（現在値>Pivot かつ 出来高急増）: {is_breakout}

--- リスク・リワード計算 ---
・想定Stop Loss（直近20日最安値）: {facts.get('stop_loss', 0):,.1f} 円
・暫定Target: {facts.get('target', 0):,.1f} 円
・R:R 比率: {rr_ratio:.2f}
"""

    prompt = f"""
あなたはローリスク・ハイリターンを狙う冷徹かつ優秀なスイングトレーダー「参考ちゃん」です。
以下のPythonが計算したテクニカルデータ（事実）のみに基づいて、現在の局面とアクションプランをMarkdownの箇条書き等の読みやすい形式で回答してください。

{fact_text}

【厳守すべきルール】
ルール1: 「落ちるナイフ状態」がTrueであれば、どんな理由があろうと絶対に『見送り』を推奨すること。
ルール2: 「R:R（リスクリワード）比率」が3.0未満の場合は、旨味が少ない勝負として明確に警告すること。
ルール3: 断定的な予測は避け、ストップロスと利確目標を明記した戦略を具体的に提示すること。

【出力フォーマット】必ず以下の3つのセクションに分けて出力してください。
### ⚔️ 総合判定
【見送り】【監視継続（押し目待ち）】【打診買い】【ブレイクアウト（Go）】などの端的な結論を最初に述べる。

### 📊 テクニカル＆R:R評価
Pythonで計算したSMAの状態やR:R比率を解説しつつ、現状のチャートの形を評価する。

### 🎯 アクションプラン
具体的なStop Lossライン（撤退線）とTarget（目標値）を明記した、次に取るべき行動の提案。
"""
    return prompt

def analyze_swing_trade_with_gemini(ticker: str, technical_facts: dict) -> str:
    """
    個別銘柄のスイングトレード診断をGeminiで実行する
    """
    api_key = _get_api_key()
    if not api_key:
        return "⚠️ エラー: Gemini APIキーが設定されていません。"

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        
        # gemini-2.0-flash を使用する
        model = genai.GenerativeModel("gemini-2.0-flash")
        
        prompt = _build_swing_prompt(ticker, technical_facts)
        response = model.generate_content(prompt)
        
        return response.text
        
    except Exception as e:
        # モデル名エラーのフォールバック
        try:
            model = genai.GenerativeModel("gemini-pro")
            response = model.generate_content(prompt)
            return response.text
        except Exception as fallback_e:
            return f"⚠️ 診断中にエラーが発生しました。\n\n詳細: {str(e)} / {str(fallback_e)}"
