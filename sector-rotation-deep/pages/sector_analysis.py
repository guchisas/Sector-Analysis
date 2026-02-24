# -*- coding: utf-8 -*-
"""
セクター分析ページ
- セクター別騰落率バーチャート
- セクター内銘柄一覧（RSI・SMA乖離率付き）
- セクターフィルタリング
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.db_manager import (
    get_latest_data, get_latest_date, get_sector_summary,
    db_exists
)
from utils.styles import section_header, stock_card, empty_state, metric_card
from utils.constants import SECTORS


def render():
    """セクター分析ページをレンダリングする"""
    st.markdown("# 📊 セクター分析")
    st.caption("業種別の資金流入状況とテクニカル指標を分析")

    if not db_exists():
        st.markdown(empty_state(
            "データがありません。ダッシュボードの「データを最新化」ボタンを押してください。", "📭"
        ), unsafe_allow_html=True)
        return

    latest_date = get_latest_date()
    latest_data = get_latest_data()
    sector_summary = get_sector_summary()

    if sector_summary.empty:
        st.warning("セクターデータが見つかりません。")
        return

    st.markdown(f"**分析日: {latest_date}**")

    # ===== セクター別平均RSIチャート =====
    st.markdown(section_header("セクター別 平均RSI", "📊"), unsafe_allow_html=True)

    chart_data = sector_summary.sort_values("avg_rsi", ascending=True)

    # RSIの色分け
    def rsi_color(val):
        if val <= 30:
            return "#FF4B4B"  # 売られすぎ（赤）
        elif val >= 70:
            return "#00D26A"  # 買われすぎ（緑）
        else:
            return "#4C9BE8"  # 中間（青）

    colors = [rsi_color(v) for v in chart_data["avg_rsi"]]

    fig_rsi = go.Figure(data=[
        go.Bar(
            x=chart_data["avg_rsi"],
            y=chart_data["sector"],
            orientation="h",
            marker_color=colors,
            text=chart_data["avg_rsi"].round(1),
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>平均RSI: %{x:.1f}<extra></extra>",
        )
    ])
    fig_rsi.add_vline(x=30, line_dash="dash", line_color="#FF4B4B", annotation_text="売られすぎ(30)")
    fig_rsi.add_vline(x=70, line_dash="dash", line_color="#00D26A", annotation_text="買われすぎ(70)")
    fig_rsi.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=max(400, len(chart_data) * 28),
        margin=dict(l=150, r=60, t=20, b=20),
        xaxis_title="平均RSI",
        font=dict(size=11),
    )
    st.plotly_chart(fig_rsi, use_container_width=True)

    # ===== セクター別PPO（移動平均乖離率）チャート =====
    st.markdown(section_header("セクター別 PPO（移動平均乖離率）", "📉"), unsafe_allow_html=True)

    ppo_data = sector_summary.sort_values("avg_ppo", ascending=True)
    ppo_colors = ["#00D26A" if v >= 0 else "#FF4B4B" for v in ppo_data["avg_ppo"]]

    fig_ppo = go.Figure(data=[
        go.Bar(
            x=ppo_data["avg_ppo"],
            y=ppo_data["sector"],
            orientation="h",
            marker_color=ppo_colors,
            text=ppo_data["avg_ppo"].round(2),
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>PPO: %{x:.2f}%<extra></extra>",
        )
    ])
    fig_ppo.add_vline(x=0, line_dash="solid", line_color="#888")
    fig_ppo.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=max(400, len(ppo_data) * 28),
        margin=dict(l=150, r=60, t=20, b=20),
        xaxis_title="PPO (%)",
        font=dict(size=11),
    )
    st.plotly_chart(fig_ppo, use_container_width=True)

    # ===== セクター別銘柄一覧 =====
    st.markdown(section_header("セクター別銘柄一覧", "🔍"), unsafe_allow_html=True)

    # セクター選択
    available_sectors = sorted(sector_summary["sector"].unique().tolist())
    selected_sector = st.selectbox(
        "セクターを選択",
        available_sectors,
        index=0,
    )

    if selected_sector:
        sector_stocks = latest_data[latest_data["sector"] == selected_sector].copy()

        if not sector_stocks.empty:
            # セクターKPI
            col1, col2, col3 = st.columns(3)
            with col1:
                avg_rsi = sector_stocks["rsi"].mean()
                rsi_label = "😨 売られすぎ" if avg_rsi <= 30 else ("😤 買われすぎ" if avg_rsi >= 70 else "😐 中立")
                st.markdown(metric_card("平均RSI", f"{avg_rsi:.1f}", "📊", rsi_label), unsafe_allow_html=True)
            with col2:
                avg_vr = sector_stocks["volume_ratio"].mean()
                st.markdown(metric_card("平均出来高倍率", f"{avg_vr:.2f}x", "📈"), unsafe_allow_html=True)
            with col3:
                avg_ppo = sector_stocks["ppo"].mean()
                ppo_sign = "+" if avg_ppo >= 0 else ""
                st.markdown(metric_card("平均PPO", f"{ppo_sign}{avg_ppo:.2f}%", "📉"), unsafe_allow_html=True)

            # 銘柄カード表示
            sort_option = st.radio(
                "ソート",
                ["出来高倍率（高い順）", "RSI（低い順）", "PPO（低い順）"],
                horizontal=True,
            )
            if sort_option == "出来高倍率（高い順）":
                sector_stocks = sector_stocks.sort_values("volume_ratio", ascending=False)
            elif sort_option == "RSI（低い順）":
                sector_stocks = sector_stocks.sort_values("rsi", ascending=True)
            else:
                sector_stocks = sector_stocks.sort_values("ppo", ascending=True)

            for _, row in sector_stocks.iterrows():
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
            st.info(f"「{selected_sector}」セクターの銘柄データがありません。")
