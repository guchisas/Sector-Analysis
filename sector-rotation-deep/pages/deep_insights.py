# -*- coding: utf-8 -*-
"""
AIインサイトページ
- Gemini AIレポート全文表示
- ニュース原文の確認機能（デバッグ用）
- 売られすぎ銘柄・買われすぎ銘柄リスト
"""

import streamlit as st
import pandas as pd
import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# モジュールのインポート（エラーハンドリング付き）
try:
    from modules.db_manager import (
        db_exists, get_latest_date, get_sector_summary,
        get_oversold_stocks, get_volume_surge_stocks, get_latest_data
    )
    from modules.ai_analyzer import analyze_with_gemini
    from modules.news_fetcher import fetch_news_summary
    from utils.styles import section_header, stock_card, empty_state, metric_card
except ImportError as e:
    st.error(f"モジュールの読み込みに失敗しました: {e}")
    st.stop()

def render():
    """AIインサイトページをレンダリングする"""
    st.markdown("# 🤖 AIインサイト")
    st.caption("Gemini 1.5 Pro によるセクターローテーション深層分析")

    # DBチェック
    if not db_exists():
        st.markdown(empty_state(
            "データがありません。ダッシュボードの「データを最新化」ボタンを押してください。", "📭"
        ), unsafe_allow_html=True)
        return

    # データ取得
    latest_date = get_latest_date()
    sector_summary = get_sector_summary()
    oversold = get_oversold_stocks()
    volume_surge = get_volume_surge_stocks()

    # ヘッダーエリア（日付と再分析ボタン）
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"**分析対象日: {latest_date}**")
    with col2:
        if st.button("🔄 AI再分析", use_container_width=True, type="primary"):
            # キャッシュをクリアして再分析
            if "ai_insight" in st.session_state:
                del st.session_state["ai_insight"]
            if "ai_insight_date" in st.session_state:
                del st.session_state["ai_insight_date"]
            if "news_cache" in st.session_state:
                del st.session_state["news_cache"]
            st.rerun()

    # ===== AIレポートセクション =====
    st.markdown(section_header("AI深層分析レポート", "🧠"), unsafe_allow_html=True)

    # ニュースとAI分析の実行（キャッシュ利用）
    if "ai_insight" not in st.session_state or st.session_state.get("ai_insight_date") != latest_date:
        with st.spinner("🤖 市場データを分析し、ニュースと照合しています...（約30秒）"):
            try:
                # ニュース取得
                news_text = fetch_news_summary(max_articles=15)
                st.session_state["news_cache"] = news_text # デバッグ用に保存
                
                # AI分析実行
                insight = analyze_with_gemini(sector_summary, oversold, volume_surge, news_text)
                
                # 結果を保存
                st.session_state["ai_insight"] = insight
                st.session_state["ai_insight_date"] = latest_date
                
            except Exception as e:
                st.error(f"分析中にエラーが発生しました: {e}")
                return

    # レポート表示
    st.markdown(f"""
    <div class="ai-insight-card" style="padding: 1.5rem; background-color: #f8f9fa; border-radius: 10px; border-left: 5px solid #4CAF50;">
        <h4 style="margin-top:0;">🧠 Gemini AI 市場分析 <span style="color:#666; font-size:0.8rem;">{latest_date}</span></h4>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown(st.session_state.get("ai_insight", ""))

    # 【重要】ニュース原文の確認（デバッグ用）
    # ここで「アンソロピック」などの単語が含まれているか確認できます
    st.markdown("---")
    with st.expander("🔍 AIが読んだニュース原文を確認する（ここに含まれない情報は分析されません）"):
        news_debug = st.session_state.get("news_cache", "ニュースデータがありません")
        st.text(news_debug)

    st.markdown("---")

    # ===== 売られすぎ銘柄 =====
    st.markdown(section_header("売られすぎ銘柄（RSI ≤ 30）", "📉"), unsafe_allow_html=True)

    if not oversold.empty:
        st.markdown(metric_card("該当銘柄数", str(len(oversold)), "😨"), unsafe_allow_html=True)
        # 上位12銘柄を表示（グリッドレイアウト）
        cols = st.columns(3)
        for i, (_, row) in enumerate(oversold.iterrows()):
            with cols[i % 3]:
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
            cols = st.columns(3)
            for i, (_, row) in enumerate(overbought.head(12).iterrows()):
                 with cols[i % 3]:
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
        cols = st.columns(3)
        for i, (_, row) in enumerate(volume_surge.head(12).iterrows()):
             with cols[i % 3]:
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
