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

# ページリスト
_PAGES = ["🏠 ダッシュボード", "📊 セクター分析", "📋 銘柄チャート", "🎯 四季報スナイパー", "🤖 AIインサイト", "📰 ニュースフィード", "📘 運用ガイド"]

# 外部ページ（dashboard.pyなど）からの遷移リクエストを検知
_default_index = 0
if "_nav_target" in st.session_state:
    _target = st.session_state.pop("_nav_target")
    if _target in _PAGES:
        _default_index = _PAGES.index(_target)
    # session_stateに既存のcurrent_pageがあるとindexが無視されるため削除
    st.session_state.pop("current_page", None)

with st.sidebar:
    st.markdown("## 📈 セクター分析")
    st.markdown("---")

    page = st.radio(
        "ページ選択",
        _PAGES,
        index=_default_index,
        key="current_page",
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
elif page == "🎯 四季報スナイパー":
    from pages import shikiho_edge
    shikiho_edge.render()
elif page == "🤖 AIインサイト":
    from pages import deep_insights
    deep_insights.render()
elif page == "📰 ニュースフィード":
    from pages import news_feed
    news_feed.render()
elif page == "📘 運用ガイド":
    from pages import guide
    guide.render()
