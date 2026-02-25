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
from datetime import datetime, timedelta

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
from modules.market_overview import fetch_market_overview, render_market_panel_html
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

    # 現在のJST時刻と最終更新情報をヘッダー下に表示
    from datetime import timezone, timedelta as td
    jst = timezone(td(hours=9))
    now_jst = datetime.now(jst)
    next_hour = f"{(now_jst.hour + 1) % 24:02d}:{now_jst.minute:02d}"
    st.caption(f"📅 データ: {latest_date} ｜ 🕐 現在 {now_jst.strftime('%H:%M')} (JST) ｜ 次回更新: {next_hour} 以降")

    # ===== 市場概況（地合い）エリア =====
    st.markdown(section_header("市場概況（地合い）", "🌐"), unsafe_allow_html=True)

    # サーバーサイドキャッシュ（全ユーザー共有・1時間更新）
    @st.cache_data(ttl=3600, show_spinner="📡 主要指数を取得中...")
    def _cached_market_overview():
        return fetch_market_overview()

    market_data = _cached_market_overview()

    # CSS Gridベースのレスポンシブパネルを1ブロックのHTMLとして出力
    st.markdown(render_market_panel_html(market_data), unsafe_allow_html=True)

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

    # サーバーサイドキャッシュ（全ユーザー共有・1時間更新）
    @st.cache_data(ttl=3600, show_spinner="🤖 AI分析を実行中...")
    def _cached_ai_insight(_date: str):
        """日付をキーにして、日付が変わったらキャッシュを更新する"""
        news_text = fetch_news_summary(max_articles=10)
        result = analyze_with_gemini(sector_summary, oversold, volume_surge, news_text)
        # 分析実行時刻を日本時間（JST = UTC+9）で記録
        from datetime import timezone, timedelta as td
        jst = timezone(td(hours=9))
        return result, datetime.now(jst).strftime("%H:%M")

    ai_text, analyzed_at = _cached_ai_insight(latest_date)

    # 次回更新可能時刻を計算
    try:
        h, m = map(int, analyzed_at.split(":"))
        next_update = f"{(h + 1) % 24:02d}:{m:02d}"
    except Exception:
        next_update = "1時間後"

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
    st.caption(f"🕐 {analyzed_at} 時点の分析です ｜ 次回更新: {next_update} 以降 ｜ 詳細は「AIインサイト」ページへ")

    # ===== セクター別出来高ヒートマップ =====
    st.markdown(section_header("セクター別出来高急増率ヒートマップ", "🗺️"), unsafe_allow_html=True)

    if not sector_summary.empty:
        # 出来高倍率でソート（昇順 → 上が高い値）
        chart_data = sector_summary.sort_values("avg_volume_ratio", ascending=True)

        # 1.0倍以上 → 緑グラデ（活況）、1.0倍未満 → 赤グラデ（低調）
        colors = [
            f"rgba(0, 210, 106, {min(0.4 + v * 0.3, 0.95)})" if v >= 1.0
            else f"rgba(255, 75, 75, {min(0.4 + v * 0.3, 0.85)})"
            for v in chart_data["avg_volume_ratio"]
        ]

        fig = go.Figure(data=[
            go.Bar(
                y=chart_data["sector"],
                x=chart_data["avg_volume_ratio"],
                orientation="h",
                marker=dict(
                    color=colors,
                    line=dict(width=0),
                ),
                text=chart_data["avg_volume_ratio"].apply(lambda v: f"{v:.2f}x"),
                textposition="outside",
                textfont=dict(size=10, color="#AAA"),
                hovertemplate="<b>%{y}</b><br>出来高倍率: %{x:.2f}x<extra></extra>",
            )
        ])
        # 1.0倍の基準線
        fig.add_vline(
            x=1.0, line_dash="dot", line_color="rgba(255,255,255,0.25)", line_width=1,
            annotation_text="1.0x", annotation_position="top",
            annotation_font_size=9, annotation_font_color="#666",
        )
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=max(650, len(chart_data) * 26),
            margin=dict(l=110, r=50, t=10, b=30),
            xaxis=dict(
                title="平均出来高倍率",
                title_font_size=11,
                gridcolor="rgba(255,255,255,0.04)",
                zeroline=False,
            ),
            yaxis=dict(
                tickfont=dict(size=10),
            ),
            font=dict(size=11),
            bargap=0.25,
            dragmode=False,
        )
        st.plotly_chart(fig, use_container_width=True, config={
            "scrollZoom": False,
            "displayModeBar": False,
            "staticPlot": True,
        })

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
