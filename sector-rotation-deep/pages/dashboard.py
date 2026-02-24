# -*- coding: utf-8 -*-
"""
ダッシュボードページ
- KPIカード（総銘柄数、セクター数、急騰銘柄数、最新日付）
- セクター別出来高ヒートマップ
- 出来高急増TOP20テーブル（カード型表示）
- AIインサイト概要
- データ更新ボタン
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.db_manager import (
    db_exists, get_latest_date, get_latest_data,
    get_sector_summary, get_volume_surge_stocks,
    get_oversold_stocks, upsert_market_data, init_db
)
from modules.market_data_fetcher import fetch_with_streamlit_progress
from modules.technical_analysis import calculate_all_indicators, get_latest_indicators
from modules.jpx_stock_list import get_all_stocks, get_all_tickers, get_ticker_to_sector, get_ticker_to_name
from modules.ai_analyzer import analyze_with_gemini
from modules.news_fetcher import fetch_news_summary
from utils.styles import metric_card, stock_card, section_header, empty_state


def _run_data_update():
    """データ取得・テクニカル計算・DB保存を実行する"""
    stocks = get_all_stocks()
    tickers = [t for t, _, _ in stocks]
    sector_map = get_ticker_to_sector()
    name_map = get_ticker_to_name()

    # yfinanceでデータ取得
    st.info("📡 市場データをyfinanceから取得中...")
    raw_data = fetch_with_streamlit_progress(tickers, period="6mo")

    if not raw_data:
        st.error("❌ データを取得できませんでした。ネットワーク接続を確認してください。")
        return

    # テクニカル指標計算 & DB保存
    st.info("🔧 テクニカル指標を計算中...")
    records = []
    progress_bar = st.progress(0)
    total = len(raw_data)

    for idx, (ticker, df) in enumerate(raw_data.items()):
        try:
            indicators = get_latest_indicators(df)
            if indicators and indicators.get("close"):
                indicators["ticker"] = ticker
                indicators["name"] = name_map.get(ticker, "")
                indicators["sector"] = sector_map.get(ticker, "不明")
                records.append(indicators)
        except Exception:
            pass

        progress_bar.progress((idx + 1) / total)

    progress_bar.empty()

    if records:
        upsert_market_data(records)
        st.success(f"✅ {len(records)} 銘柄のデータを更新しました！")
    else:
        st.warning("⚠️ 有効なデータが取得できませんでした。")


def render():
    """ダッシュボードページをレンダリングする"""
    # ヘッダー
    col_title, col_btn = st.columns([3, 1])
    with col_title:
        st.markdown("# 日本株セクターローテーション分析")
        st.caption("スイングトレード向け資金流入分析ダッシュボード")
    with col_btn:
        if st.button("🔄 データを最新化", use_container_width=True, type="primary"):
            _run_data_update()
            st.rerun()

    # データ存在チェック
    if not db_exists():
        st.markdown(empty_state(
            "まだデータがありません。右上の「データを最新化」ボタンを押して、最新の市場データを取得してください。",
            "🚀"
        ), unsafe_allow_html=True)
        return

    # 最新データ取得
    latest_date = get_latest_date()
    latest_data = get_latest_data()
    sector_summary = get_sector_summary()
    volume_surge = get_volume_surge_stocks()
    oversold = get_oversold_stocks()

    # ===== KPIカード =====
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(metric_card("総銘柄数", str(len(latest_data)), "📋"), unsafe_allow_html=True)
    with col2:
        sector_count = latest_data["sector"].nunique() if not latest_data.empty else 0
        st.markdown(metric_card("セクター数", str(sector_count), "🏷️"), unsafe_allow_html=True)
    with col3:
        surge_count = len(volume_surge)
        st.markdown(metric_card("急騰銘柄数", str(surge_count), "🚀"), unsafe_allow_html=True)
    with col4:
        st.markdown(metric_card("最新日付", latest_date or "N/A", "📅"), unsafe_allow_html=True)

    # ===== AIインサイト概要 =====
    st.markdown(section_header("本日のAIインサイト", "🧠"), unsafe_allow_html=True)

    # キャッシュされたAI分析結果の取得
    if "ai_insight" not in st.session_state:
        with st.spinner("🤖 AI分析を実行中..."):
            news_text = fetch_news_summary(max_articles=10)
            insight = analyze_with_gemini(sector_summary, oversold, volume_surge, news_text)
            st.session_state["ai_insight"] = insight
            st.session_state["ai_insight_date"] = latest_date

    # 日付が変わった場合はキャッシュを更新
    if st.session_state.get("ai_insight_date") != latest_date:
        with st.spinner("🤖 AI分析を更新中..."):
            news_text = fetch_news_summary(max_articles=10)
            insight = analyze_with_gemini(sector_summary, oversold, volume_surge, news_text)
            st.session_state["ai_insight"] = insight
            st.session_state["ai_insight_date"] = latest_date

    # AIインサイトカード表示
    ai_text = st.session_state.get("ai_insight", "")
    # 概要のみ表示（最初の500文字）
    summary_text = ai_text[:500] + "..." if len(ai_text) > 500 else ai_text
    st.markdown(f"""
    <div class="ai-insight-card">
        <h4>⚡ AIインサイト <span style="color:#666; font-size:0.8rem;">{latest_date}</span></h4>
        <div style="color:#CCC; font-size:0.9rem; line-height:1.6;">
            {summary_text.replace(chr(10), '<br>')}
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.caption("💡 詳細は「AIインサイト」ページで確認できます")

    # ===== セクター別出来高ヒートマップ =====
    st.markdown(section_header("セクター別出来高急増率ヒートマップ", "🗺️"), unsafe_allow_html=True)

    if not sector_summary.empty:
        # 出来高倍率でソート
        chart_data = sector_summary.sort_values("avg_volume_ratio", ascending=False)

        # カラースケールを適用
        colors = ["#FF4B4B" if v < 1.0 else "#00D26A" for v in chart_data["avg_volume_ratio"]]

        fig = go.Figure(data=[
            go.Bar(
                x=chart_data["sector"],
                y=chart_data["avg_volume_ratio"],
                marker_color=colors,
                text=chart_data["avg_volume_ratio"].round(2),
                textposition="auto",
                hovertemplate="<b>%{x}</b><br>出来高倍率: %{y:.2f}x<extra></extra>",
            )
        ])
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=400,
            margin=dict(l=20, r=20, t=20, b=80),
            xaxis_tickangle=-45,
            yaxis_title="平均出来高倍率",
            font=dict(size=11),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ===== 出来高急増 TOP20 =====
    st.markdown(section_header("出来高急増銘柄 TOP20", "🚀"), unsafe_allow_html=True)

    if not volume_surge.empty:
        top20 = volume_surge.head(20)

        # カード型表示（スマホフレンドリー）
        for _, row in top20.iterrows():
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
        st.info("出来高急増銘柄はありません。")
