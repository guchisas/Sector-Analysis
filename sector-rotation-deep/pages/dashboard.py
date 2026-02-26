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

    # ===== ステータスバー =====
    sector_count = latest_data["sector"].nunique() if not latest_data.empty else 0
    surge_count = len(volume_surge)
    oversold_count = len(oversold)

    st.markdown(f"""
    <div class="status-bar">
        <span class="sb-item">📅 <span class="sb-val">{latest_date or 'N/A'}</span></span>
        <span class="sb-divider">│</span>
        <span class="sb-item">🏢 銘柄 <span class="sb-val">{len(latest_data)}</span></span>
        <span class="sb-divider">│</span>
        <span class="sb-item">🏷️ セクター <span class="sb-val">{sector_count}</span></span>
        <span class="sb-divider">│</span>
        <span class="sb-item">🚀 急騰 <span class="sb-val">{surge_count}</span></span>
        <span class="sb-divider">│</span>
        <span class="sb-item">📉 売られすぎ <span class="sb-val">{oversold_count}</span></span>
    </div>
    """, unsafe_allow_html=True)

    # ===== 市場概況（地合い）エリア =====
    st.markdown(section_header("市場概況（地合い）", "🌐"), unsafe_allow_html=True)

    # サーバーサイドキャッシュ（全ユーザー共有・1時間更新）
    @st.cache_data(ttl=3600, show_spinner="📡 主要指数を取得中...")
    def _cached_market_overview():
        return fetch_market_overview()

    market_data = _cached_market_overview()

    # --- HTMLカード（閉じた状態のサマリー）+ Expander内にミニチャート ---
    st.markdown(render_market_panel_html(market_data), unsafe_allow_html=True)

    # Expander型ミニチャート（4指数を2列で並べる）
    idx_keys = ["nikkei", "topix", "growth250", "usdjpy"]
    cols_chart = st.columns(2)
    for i, key in enumerate(idx_keys):
        data = market_data.get(key, {})
        history = data.get("history_1m", [])
        history_dates = data.get("history_dates", [])
        name = data.get("name", key)
        icon = data.get("icon", "📊")

        with cols_chart[i % 2]:
            with st.expander(f"{icon} {name} — 過去1ヶ月チャート", expanded=False):
                if history and len(history) > 1:
                    chart_df = pd.DataFrame({
                        "日付": history_dates,
                        "終値": history,
                    }).set_index("日付")
                    st.area_chart(chart_df, color="#4C9BE8", height=180)
                else:
                    st.caption("ヒストリカルデータを取得できませんでした。")



    # ===== AIインサイト概要 =====
    st.markdown(section_header("本日のAIインサイト", "🧠"), unsafe_allow_html=True)

    from modules.ai_analyzer import get_shared_ai_insight
    from modules.db_manager import get_db_last_modified
    
    db_version = get_db_last_modified()
    ai_text, analyzed_at = get_shared_ai_insight(latest_date, db_version)

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

    # ===== セクター別出来高(天気図) =====
    st.markdown(section_header("セクター(天気図) - 出来高と勢い", "🗺️"), unsafe_allow_html=True)

    if not sector_summary.empty:
        # Treemap用のデータ準備
        # 箱の大きさ: 銘柄数(stock_count)
        # 色: 出来高倍率(avg_volume_ratio)
        chart_data = sector_summary.copy()
        
        # 1.0倍を基準（中央）とした赤・緑のカラースケール
        max_val = max(chart_data["avg_volume_ratio"].max(), 1.0)
        min_val = min(chart_data["avg_volume_ratio"].min(), 1.0)
        
        # 値の範囲を調整し、1.0を中心とする
        diff = max(abs(max_val - 1.0), abs(1.0 - min_val))
        range_color = [1.0 - diff, 1.0 + diff] if diff > 0 else [0, 2]

        fig = px.treemap(
            chart_data,
            path=[px.Constant("全セクター"), 'sector'],
            values='stock_count',
            color='avg_volume_ratio',
            color_continuous_scale=[[0, "rgb(255, 75, 75)"], [0.5, "rgb(40, 40, 40)"], [1, "rgb(0, 210, 106)"]],
            color_continuous_midpoint=1.0,
            range_color=range_color,
            custom_data=['avg_volume_ratio', 'stock_count']
        )
        
        fig.update_traces(
            textinfo="label+text",
            texttemplate="<b>%{label}</b><br>出来高: %{customdata[0]:.2f}x<br>銘柄数: %{customdata[1]}",
            hovertemplate="<b>%{label}</b><br>出来高倍率: %{customdata[0]:.2f}x<br>銘柄数: %{customdata[1]}<extra></extra>",
            marker=dict(line=dict(width=1, color="#111"))
        )
        
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=600,
            margin=dict(l=10, r=10, t=30, b=10),
            coloraxis_colorbar=dict(
                title="出来高倍率",
                thicknessmode="pixels", thickness=15,
                lenmode="pixels", len=300,
                yanchor="middle", y=0.5,
                ticks="outside", ticksuffix="x",
                dtick=0.5
            )
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
