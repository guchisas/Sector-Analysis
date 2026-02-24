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
            sector_text += (
                f"- {row['sector']}: "
                f"平均RSI={row.get('avg_rsi', 'N/A'):.1f}, "
                f"平均出来高倍率={row.get('avg_volume_ratio', 'N/A'):.2f}, "
                f"平均PPO={row.get('avg_ppo', 'N/A'):.2f}, "
                f"銘柄数={row.get('stock_count', 0)}\n"
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

    prompt = f"""あなたはプロのトレーダー兼マーケットアナリストです。
以下のデータを俯瞰的に分析し、資金循環（セクターローテーション）の観点から、
次に注目すべきトレンドとスイングトレード（数日〜1週間）のチャンスを日本語で予測してください。

分析は以下の構成で行ってください：
1. **📊 マーケット概況**: 現在の市場全体のムード（データから読み取れる傾向）
2. **🔄 資金流入セクター**: 出来高やRSIから「資金が流入している」と判断されるセクター
3. **📉 推奨ローテーション先**: 次に資金が流入する可能性が高いセクターの予測と根拠
4. **⚡ 注目銘柄TOP5**: スイングトレードの具体的な候補（ティッカー・理由付き）
5. **⚠️ リスク要因**: 注意すべきリスクやネガティブシグナル

{sector_text}
{oversold_text}
{volume_text}
{news_text}

データに基づいた具体的かつ実用的な分析をお願いします。"""

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
        
        # 2.0は無料枠制限に引っかかりやすいため、より安定している 1.5-flash に意図的にダウングレードします
        model = genai.GenerativeModel('models/gemini-1.5-flash')

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

