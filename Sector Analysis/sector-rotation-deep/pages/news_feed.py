# -*- coding: utf-8 -*-
"""
ニュースフィードページ
- RSSフィードからの最新ニュース一覧
- ソース別フィルタリング
"""

import streamlit as st

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.news_fetcher import fetch_news, RSS_FEEDS
from utils.styles import section_header, news_card, empty_state


def render():
    """ニュースフィードページをレンダリングする"""
    st.markdown("# 📰 ニュースフィード")
    st.caption("株式市場関連の最新ニュースを一覧表示")

    # フィルタリングオプション
    col1, col2 = st.columns([2, 1])
    with col1:
        source_names = ["すべて"] + [f["name"] for f in RSS_FEEDS]
        selected_source = st.selectbox("ソース", source_names)
    with col2:
        hours = st.selectbox("期間", [6, 12, 24, 48], index=2, format_func=lambda x: f"直近{x}時間")

    # ニュース取得
    with st.spinner("📡 ニュースを取得中..."):
        articles = fetch_news(hours=hours)

    # ソースフィルタリング
    if selected_source != "すべて":
        articles = [a for a in articles if a["source"] == selected_source]

    # 表示
    st.markdown(section_header(f"📰 ニュース一覧（{len(articles)}件）", "📰"), unsafe_allow_html=True)

    if articles:
        for article in articles:
            st.markdown(
                news_card(
                    title=article["title"],
                    link=article["link"],
                    pub_date=f"{article['published']} | {article['source']}",
                ),
                unsafe_allow_html=True,
            )
    else:
        st.markdown(empty_state(
            "指定期間内のニュースが見つかりませんでした。期間を広げてお試しください。", "📭"
        ), unsafe_allow_html=True)
