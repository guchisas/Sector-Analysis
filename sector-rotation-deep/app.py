# -*- coding: utf-8 -*-
"""
Japan Stock Sector Rotation Deep Dive
メインアプリケーションエントリポイント
"""

import streamlit as st
import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.styles import get_custom_css
from modules.db_manager import init_db, db_exists

# ===== ページ設定 =====
st.set_page_config(
    page_title="日本株セクターローテーション分析",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "日本株セクターローテーション Deep Dive - スイングトレード向け分析ツール"
    }
)

# ===== カスタムCSS注入 =====
st.markdown(get_custom_css(), unsafe_allow_html=True)

# ===== DB初期化 =====
init_db()

# ===== サイドバー =====
with st.sidebar:
    st.markdown("## 📈 セクター分析")
    st.markdown("---")

    # ナビゲーション
    page = st.radio(
        "ページ選択",
        ["🏠 ダッシュボード", "📊 セクター分析", "📋 銘柄チャート", "🤖 AIインサイト", "📰 ニュースフィード"],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.caption("© 2026 Sector Rotation Deep Dive")

# ===== メインコンテンツ =====
if page == "🏠 ダッシュボード":
    from pages import dashboard
    dashboard.render()
elif page == "📊 セクター分析":
    from pages import sector_analysis
    sector_analysis.render()
elif page == "📋 銘柄チャート":
    from pages import stock_chart
    stock_chart.render()
elif page == "🤖 AIインサイト":
    from pages import deep_insights
    deep_insights.render()
elif page == "📰 ニュースフィード":
    from pages import news_feed
    news_feed.render()
