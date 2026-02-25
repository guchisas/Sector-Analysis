# -*- coding: utf-8 -*-
"""
AIインサイトページ
- Gemini AIレポート全文表示
- 売られすぎ銘柄・買われすぎ銘柄リスト
- AI再分析ボタン
"""

import streamlit as st
import pandas as pd
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.db_manager import (
    db_exists, get_latest_date, get_sector_summary,
    get_oversold_stocks, get_volume_surge_stocks, get_latest_data
)
from modules.ai_analyzer import analyze_with_gemini
from modules.news_fetcher import fetch_news_summary
from utils.styles import section_header, stock_card, empty_state, metric_card


def render():
    """AIインサイトページをレンダリングする"""
    st.markdown("# 🤖 AIインサイト")
    st.caption("Gemini AIによるセクターローテーション深層分析")

    if not db_exists():
        st.markdown(empty_state(
            "データがありません。ダッシュボードの「データを最新化」ボタンを押してください。", "📭"
        ), unsafe_allow_html=True)
        return

    latest_date = get_latest_date()
    sector_summary = get_sector_summary()
    oversold = get_oversold_stocks()
    volume_surge = get_volume_surge_stocks()

    # ===== AIレポート =====
    st.markdown(section_header("AI深層分析レポート", "🧠"), unsafe_allow_html=True)

    # サーバーサイドキャッシュ（全ユーザー共有・1時間更新）
    @st.cache_data(ttl=3600, show_spinner="🤖 Gemini AIが分析中...（30秒ほどかかる場合があります）")
    def _cached_full_ai_insight(_date: str):
        """日付をキーにして、日付が変わったらキャッシュを更新する"""
        news_text = fetch_news_summary(max_articles=15)
        result = analyze_with_gemini(sector_summary, oversold, volume_surge, news_text)
        return result, datetime.now().strftime("%H:%M")

    insight, analyzed_at = _cached_full_ai_insight(latest_date)

    # 次回更新可能時刻を計算
    try:
        h, m = map(int, analyzed_at.split(":"))
        next_update = f"{(h + 1) % 24:02d}:{m:02d}"
    except Exception:
        next_update = "1時間後"

    # AI再分析ボタン（注意書き付き）
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"**分析対象日: {latest_date}**")
        st.caption(f"🕐 {analyzed_at} 時点の分析です ｜ 次回更新可能: {next_update} 以降")
    with col2:
        if st.button("🔄 AI再分析", use_container_width=True, type="primary"):
            _cached_full_ai_insight.clear()
            st.rerun()

    st.info(f"⚠️ この分析は全ユーザーで共有されています。「再分析」ボタンを押すとAPI制限を消費するため、{next_update} 以降に押してください。")

    # レポート全文表示
    st.markdown(f"""
    <div class="ai-insight-card">
        <h4>🧠 Gemini AI 分析レポート <span style="color:#666; font-size:0.8rem;">{latest_date} {analyzed_at}時点</span></h4>
    </div>
    """, unsafe_allow_html=True)
    st.markdown(insight)

    st.markdown("---")

    # ===== 売られすぎ銘柄 =====
    st.markdown(section_header("売られすぎ銘柄（RSI ≤ 30）", "📉"), unsafe_allow_html=True)

    if not oversold.empty:
        st.markdown(metric_card("該当銘柄数", str(len(oversold)), "😨"), unsafe_allow_html=True)
        for _, row in oversold.iterrows():
            st.markdown(
                stock_card(
                    ticker=row["ticker"],
                    name=row.get("name", ""),
                    sector=row.get("sector", ""),
                    close=row.get("close", 0),
                    volume=row.get("volume", 0),
                    rsi=row.get("rsi"),
                    volume_ratio=row.get("volume_ratio"),
                ),
                unsafe_allow_html=True,
            )
    else:
        st.info("RSI ≤ 30 の売られすぎ銘柄はありません。")

    # ===== 買われすぎ銘柄 =====
    st.markdown(section_header("買われすぎ銘柄（RSI ≥ 70）", "📈"), unsafe_allow_html=True)

    latest_data = get_latest_data()
    if not latest_data.empty:
        overbought = latest_data[latest_data["rsi"] >= 70].sort_values("rsi", ascending=False)
        if not overbought.empty:
            st.markdown(metric_card("該当銘柄数", str(len(overbought)), "🔥"), unsafe_allow_html=True)
            for _, row in overbought.iterrows():
                st.markdown(
                    stock_card(
                        ticker=row["ticker"],
                        name=row.get("name", ""),
                        sector=row.get("sector", ""),
                        close=row.get("close", 0),
                        volume=row.get("volume", 0),
                        rsi=row.get("rsi"),
                        volume_ratio=row.get("volume_ratio"),
                    ),
                    unsafe_allow_html=True,
                )
        else:
            st.info("RSI ≥ 70 の買われすぎ銘柄はありません。")

    # ===== 出来高急増銘柄 =====
    st.markdown(section_header("出来高急増銘柄（2倍以上）", "🚀"), unsafe_allow_html=True)

    if not volume_surge.empty:
        st.markdown(metric_card("該当銘柄数", str(len(volume_surge)), "📊"), unsafe_allow_html=True)
        for _, row in volume_surge.head(20).iterrows():
            st.markdown(
                stock_card(
                    ticker=row["ticker"],
                    name=row.get("name", ""),
                    sector=row.get("sector", ""),
                    close=row.get("close", 0),
                    volume=row.get("volume", 0),
                    rsi=row.get("rsi"),
                    volume_ratio=row.get("volume_ratio"),
                ),
                unsafe_allow_html=True,
            )
    else:
        st.info("出来高倍率 2倍以上の銘柄はありません。")
