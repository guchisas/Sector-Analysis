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

    # ===== ミニチャート（日足/週足/月足 + 移動平均線） =====
    def _resample_ohlc(dates, opens, highs, lows, closes, freq):
        """日足OHLCデータを週足/月足にリサンプリングする"""
        df = pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": closes},
                          index=pd.to_datetime(dates))
        resampled = df.resample(freq).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
        return resampled

    def _build_candlestick_with_ma(df_ohlc, ma_periods, display_bars):
        """ローソク足 + 移動平均線のPlotly Figureを返す"""
        # 表示用に末尾から切り出し（MA計算は全データで実行）
        ma_colors = ["#FFD700", "#FF4B4B", "#00D26A"]  # 短期:黄, 中期:赤, 長期:緑
        ma_names = ["短期", "中期", "長期"]

        # MAを全期間で計算
        ma_lines = []
        for p in ma_periods:
            ma_lines.append(df_ohlc["Close"].rolling(window=p).mean())

        # 表示範囲を切り出し
        show_df = df_ohlc.tail(display_bars)
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=show_df.index, open=show_df["Open"], high=show_df["High"],
            low=show_df["Low"], close=show_df["Close"],
            increasing_line_color="#FF4B4B", increasing_fillcolor="rgba(255,75,75,0.7)",
            decreasing_line_color="#00D26A", decreasing_fillcolor="rgba(0,210,106,0.7)",
            name="価格",
        ))
        for idx_ma, (ma, p) in enumerate(zip(ma_lines, ma_periods)):
            ma_show = ma.reindex(show_df.index)
            fig.add_trace(go.Scatter(
                x=show_df.index, y=ma_show, mode="lines",
                line=dict(color=ma_colors[idx_ma], width=1.2),
                name=f"{ma_names[idx_ma]}({p})",
            ))

        y_min = float(show_df["Low"].min()) * 0.997
        y_max = float(show_df["High"].max()) * 1.003
        fig.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            height=280, margin=dict(l=5, r=5, t=10, b=20),
            xaxis=dict(rangeslider_visible=False, tickfont=dict(size=9)),
            yaxis=dict(range=[y_min, y_max], tickfont=dict(size=9), gridcolor="rgba(255,255,255,0.06)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=9)),
            dragmode=False,
        )
        return fig

    # --- Expander型ミニチャート ---
    idx_keys = ["nikkei", "topix", "growth250", "usdjpy"]
    cols_chart = st.columns(2)
    for i, key in enumerate(idx_keys):
        data = market_data.get(key, {})
        h_dates = data.get("history_dates", [])
        h_open = data.get("history_open", [])
        h_high = data.get("history_high", [])
        h_low = data.get("history_low", [])
        h_close = data.get("history_close", [])
        name = data.get("name", key)
        icon = data.get("icon", "📊")

        with cols_chart[i % 2]:
            with st.expander(f"{icon} {name} チャート", expanded=False):
                if h_close and len(h_close) > 10:
                    # 時間足切替
                    tf = st.radio("時間足", ["日足", "週足", "月足"], horizontal=True, key=f"tf_{key}")
                    daily_df = pd.DataFrame(
                        {"Open": h_open, "High": h_high, "Low": h_low, "Close": h_close},
                        index=pd.to_datetime(h_dates)
                    )
                    if tf == "日足":
                        chart_fig = _build_candlestick_with_ma(daily_df, [5, 25, 75], 60)
                    elif tf == "週足":
                        weekly_df = daily_df.resample("W").agg({"Open":"first","High":"max","Low":"min","Close":"last"}).dropna()
                        chart_fig = _build_candlestick_with_ma(weekly_df, [13, 26, 52], 52)
                    else:
                        monthly_df = daily_df.resample("ME").agg({"Open":"first","High":"max","Low":"min","Close":"last"}).dropna()
                        chart_fig = _build_candlestick_with_ma(monthly_df, [12, 24, 60], 60)
                    st.plotly_chart(chart_fig, use_container_width=True, config={"displayModeBar": False})
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

    # 構造化サマリー: AIレポートからテーマ・センチメント・注目セクターを抽出
    import re as _re
    _theme = ""
    _sentiment = ""
    _recommended = ""
    _m = _re.search(r'[\*]*市場のテーマ[：:][\*]*\s*(.+?)(?:\n|$)', ai_text)
    if _m:
        _theme = _m.group(1).strip().replace('**', '').replace('*', '')[:150]
    _m = _re.search(r'[\*]*センチメント[：:][\*]*\s*(.+?)(?:\n|$)', ai_text)
    if _m:
        _sentiment = _m.group(1).strip().replace('**', '').replace('*', '')[:150]
    _m = _re.search(r'[\*]*(?:注目銘柄|主役セクター|資金の流れ)[：:][\*]*\s*(.+?)(?:\n|$)', ai_text)
    if _m:
        _recommended = _m.group(1).strip().replace('**', '').replace('*', '')[:150]
    if not _theme and not _sentiment:
        _theme = ai_text[:300].replace('\n', ' ').strip() + "..."

    # HTMLを空行なしで結合（Streamlitのmarkdownパーサーが空行でコードブロック化するのを防止）
    _body_parts = []
    if _theme:
        _body_parts.append(f'📌 <b style="color:#4C9BE8">テーマ:</b> {_theme}')
    if _sentiment:
        _body_parts.append(f'🧭 <b style="color:#FFB347">センチメント:</b> {_sentiment}')
    if _recommended:
        _body_parts.append(f'🎯 <b style="color:#00D26A">注目:</b> {_recommended}')
    _body_html = "<br>".join(_body_parts)

    _insight_html = (
        '<div class="ai-insight-card">'
        f'<h4>⚡ AIインサイト <span style="color:#666;font-size:0.8rem">{latest_date}</span></h4>'
        f'<div style="color:#E0E0E0;font-size:0.9rem;line-height:1.8">{_body_html}</div>'
        '</div>'
    )
    st.markdown(_insight_html, unsafe_allow_html=True)
    st.caption(f"🕐 {analyzed_at} 時点の分析です ｜ 次回更新: {next_update} 以降 ｜ 詳細は「AIインサイト」ページへ")

    # ===== セクター別 騰落率ランキング =====
    st.markdown(section_header("セクター別 騰落率ランキング - 資金の流入・流出", "🏆"), unsafe_allow_html=True)

    if not sector_summary.empty:
        # データの整形
        chart_data = sector_summary.copy()
        chart_data["percent_change_fmt"] = chart_data["avg_percent_change"].apply(lambda x: f"{x:+.2f}%")
        chart_data["volume_ratio_fmt"] = chart_data["avg_volume_ratio"].apply(lambda x: f"{x:.2f}x")
        
        # 騰落率で降順にソート
        chart_data = chart_data.sort_values("avg_percent_change", ascending=False)
        
        # --------------------------------------------------
        # Top 5 / Worst 5 チャート (Altair)
        # --------------------------------------------------
        winners = chart_data.head(5).copy()
        
        # Worst 5 は昇順（ワースト1位が一番上に来るようにする）
        losers = chart_data.tail(5).copy()
        losers = losers.sort_values("avg_percent_change", ascending=True)

        import altair as alt

        col_win, col_lose = st.columns(2)

        with col_win:
            st.markdown("<h4 style='color:#FF4B4B; margin-bottom:10px;'>🔥 上昇トップ5 (Winners)</h4>", unsafe_allow_html=True)
            if not winners.empty and winners["avg_percent_change"].max() > 0:
                base_w = alt.Chart(winners).encode(
                    y=alt.Y("sector:N", sort="-x", axis=alt.Axis(title="", labels=False, ticks=False, domain=False)),
                    x=alt.X("avg_percent_change:Q", axis=alt.Axis(title="", labels=False, ticks=False, grid=False, domain=False))
                )
                # バー (右方向、エンジ/赤系)
                bars_w = base_w.mark_bar(color="#FF4B4B", cornerRadiusEnd=4, height=alt.Step(32))
                # 騰落率テキスト (バーの右端の外側)
                text_w = base_w.mark_text(align="left", dx=4, color="white", fontWeight="bold").encode(text="percent_change_fmt:N")
                # セクター名テキスト (バーの根元=内側左端)
                label_w = base_w.mark_text(align="left", dx=4, color="white").encode(x=alt.value(0), text="sector:N")
                
                fig_w = (bars_w + text_w + label_w).configure_view(strokeWidth=0).properties(height=alt.Step(32))
                st.altair_chart(fig_w, use_container_width=True)
            else:
                st.info("目立った上昇セクターはありません。")
                
        with col_lose:
            st.markdown("<h4 style='color:#00D26A; margin-bottom:10px;'>🧊 下落ワースト5 (Losers)</h4>", unsafe_allow_html=True)
            if not losers.empty and losers["avg_percent_change"].min() < 0:
                base_l = alt.Chart(losers).encode(
                    y=alt.Y("sector:N", sort="x", axis=alt.Axis(title="", labels=False, ticks=False, domain=False)),
                    x=alt.X("avg_percent_change:Q", axis=alt.Axis(title="", labels=False, ticks=False, grid=False, domain=False))
                )
                # バー (左方向、青緑/Green系)
                bars_l = base_l.mark_bar(color="#00D26A", cornerRadiusEnd=4, height=alt.Step(32))
                # 騰落率テキスト (バーの左端の外側)
                text_l = base_l.mark_text(align="right", dx=-4, color="white", fontWeight="bold").encode(text="percent_change_fmt:N")
                # セクター名テキスト (バーの根元=内側右端)
                label_l = base_l.mark_text(align="right", dx=-4, color="white").encode(x=alt.value(0), text="sector:N")
                
                fig_l = (bars_l + text_l + label_l).configure_view(strokeWidth=0).properties(height=alt.Step(32))
                st.altair_chart(fig_l, use_container_width=True)
            else:
                st.info("目立った下落セクターはありません。")
                
        # --------------------------------------------------
        # 全33業種一覧リスト (DataFrame + Style Bar)
        # --------------------------------------------------
        st.markdown("<h4 style='margin-top:20px;'>📋 全33業種 騰落率一覧</h4>", unsafe_allow_html=True)
        
        display_df = chart_data[["sector", "avg_percent_change", "avg_volume_ratio", "stock_count"]].copy()
        display_df.columns = ["セクター", "前日比 (%)", "出来高倍率 (x)", "銘柄数"]
        
        # df.style.bar() 機能を利用して表の中に騰落率の横棒グラフを描画する
        styled_df = display_df.style.format({
            "前日比 (%)": "{:+.2f}%",
            "出来高倍率 (x)": "{:.2f}x",
            "銘柄数": "{:d}"
        }).bar(
            subset=["前日比 (%)"],
            align="mid",  # 0を中央にする
            # マイナスは緑系、プラスは赤系の色で塗り分ける
            color=["rgba(0, 210, 106, 0.4)", "rgba(255, 75, 75, 0.4)"]
        )
        
        st.dataframe(
            styled_df,
            hide_index=True,
            use_container_width=True,
            height=450  # スクロール対応の高さ確保
        )

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
