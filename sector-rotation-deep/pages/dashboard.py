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
    get_sector_summary, get_advanced_sector_summary, get_sector_history_stats,
    get_volume_surge_stocks, get_oversold_stocks, upsert_market_data, init_db
)
from modules.market_data_fetcher import fetch_with_streamlit_progress
from modules.technical_analysis import calculate_all_indicators, get_latest_indicators
from modules.jpx_stock_list import get_all_stocks, get_all_tickers, get_ticker_to_sector, get_ticker_to_name
from modules.ai_analyzer import analyze_with_gemini
from modules.news_fetcher import fetch_news_summary
from modules.momentum_calculator import calculate_sector_momentum_scores
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
    # 新しいモメンタム用の詳細サマリーと履歴を取得
    sector_summary = get_advanced_sector_summary(latest_date)
    sector_history = get_sector_history_stats(latest_date, days=20)
    
    # モメンタムスコアの計算
    if not sector_summary.empty:
        sector_summary = calculate_sector_momentum_scores(sector_summary, sector_history)
    volume_surge = get_volume_surge_stocks()
    oversold = get_oversold_stocks()

    # 最終更新情報をヘッダー下に表示
    from modules.db_manager import get_db_last_modified
    from datetime import timezone, timedelta as td
    
    db_mtime = get_db_last_modified()
    jst = timezone(td(hours=9))
    
    if db_mtime > 0:
        last_updated = datetime.fromtimestamp(db_mtime, jst)
    else:
        last_updated = datetime.now(jst)
        
    next_hour = f"{(last_updated.hour + 1) % 24:02d}:{last_updated.minute:02d}"
    st.caption(f"📅 データ: {latest_date} ｜ 🕐 最終更新: {last_updated.strftime('%H:%M')} (JST) ｜ 次回更新: {next_hour} 以降")

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

    # ===== 本日の相場天気予報（相場モード） =====
    st.markdown("<br>", unsafe_allow_html=True)
    if not sector_summary.empty:
        avg_up_ratio = sector_summary["up_down_ratio"].mean() * 100
        avg_ppo_total = sector_summary["avg_ppo"].mean()
        
        if avg_up_ratio >= 60 and avg_ppo_total > 0:
            weather_icon, weather_title, weather_color, weather_desc = "☀️", "リスクオン（全面高・順張り相場）", "#00D26A", "市場全体に資金が流入しています。強いトレンドを持つトップセクターへの順張りが有効な地合いです。"
        elif avg_up_ratio <= 40 and avg_ppo_total < 0:
            weather_icon, weather_title, weather_color, weather_desc = "☔", "リスクオフ（全面安・逆張り警戒）", "#FF4B4B", "市場全体から資金が流出しています。安易なナンピンは避け、底打ちからのリバウンド（逆張り）やディフェンシブ銘柄を狙う地合いです。"
        else:
            weather_icon, weather_title, weather_color, weather_desc = "☁️", "様子見（選別物色・もみ合い相場）", "#FFA500", "全体的な方向感が乏しい状態です。資金が一部のテーマや個別銘柄に集中する「循環物色」が起きやすい地合いです。"
            
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, rgba(30,40,55,0.95) 0%, rgba(15,20,30,0.95) 100%); border-left: 5px solid {weather_color}; padding: 15px 20px; border-radius: 6px; margin-bottom: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
            <div style="font-size: 0.9rem; color: #a0a0a0; font-weight: 600; letter-spacing: 1px; margin-bottom: 5px;">本日の相場天気予報</div>
            <div style="font-size: 1.6rem; font-weight: bold; color: {weather_color}; margin-bottom: 8px;">
                {weather_icon} {weather_title}
            </div>
            <div style="font-size: 0.95rem; color: #d0d0d0; line-height: 1.5;">{weather_desc}</div>
        </div>
        """, unsafe_allow_html=True)

    # ===== 市場概況（地合い）エリア =====
    st.markdown(section_header("指標・マクロ概況", "🌐"), unsafe_allow_html=True)

    # サーバーサイドキャッシュ（全ユーザー共有・1分更新）
    # ※ページ更新時に最新データを表示できるよう、キャッシュ期間（TTL）を3600秒から60秒に短縮しました。
    @st.cache_data(ttl=60, show_spinner="📡 主要指数を取得中...")
    def _cached_market_overview():
        from datetime import datetime, timezone, timedelta
        jst = timezone(timedelta(hours=9))
        dt_str = datetime.now(jst).strftime("%H:%M")
        return fetch_market_overview(), dt_str

    market_data, market_fetch_time = _cached_market_overview()
    st.caption(f"🕖 **データ取得時刻:** 本日 {market_fetch_time} (※約1分間隔で自動更新されます)")

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

    # ===== セクター別 資金流入・流出ランキング (モメンタムスコア) =====
    st.markdown(section_header("セクター別 資金流入・流出ランキング", "🏆"), unsafe_allow_html=True)

    if not sector_summary.empty and "momentum_score" in sector_summary.columns:
        # 詳細テキストの作成
        chart_data = sector_summary.copy()
        
        # フォーマット適用
        chart_data["percent_change_fmt"] = chart_data["avg_percent_change"].apply(lambda x: f"{x:+.2f}%")
        chart_data["volume_ratio_fmt"] = chart_data["avg_volume_ratio"].apply(lambda x: f"{x:.1f}x")
        if "up_down_ratio" in chart_data.columns:
            chart_data["up_ratio_fmt"] = chart_data["up_down_ratio"].apply(lambda x: f"{x*100:.0f}%")
        else:
            chart_data["up_ratio_fmt"] = "-"
            
        chart_data["detail_text"] = chart_data.apply(
            lambda r: f"スコア:{int(r['momentum_score'])} (騰落:{r['percent_change_fmt']} | 出来高:{r['volume_ratio_fmt']} | 上昇:{r['up_ratio_fmt']})", 
            axis=1
        )
        
        # スコアで降順にソート
        chart_data = chart_data.sort_values("momentum_score", ascending=False)
        
        # --------------------------------------------------
        # セクターローテーション・レーダー（散布図）
        # --------------------------------------------------
        st.markdown("<h4 style='margin-bottom:10px;'>🗺️ セクターローテーション・レーダー</h4>", unsafe_allow_html=True)
        
        # バブルサイズ調整（最小1倍、外れ値はクリップ）
        chart_data['bubble_size'] = chart_data['avg_volume_ratio'].clip(lower=1.0, upper=5.0)
        
        # === ステルス＆ナンバリング仕様への完全刷新 ===
        
        # トップ5とワースト5を取得
        top5_df = chart_data.nlargest(5, 'momentum_score')
        worst5_df = chart_data.nsmallest(5, 'momentum_score')
        
        top5_sectors = top5_df['sector'].tolist()
        worst5_sectors = worst5_df['sector'].tolist()
        
        # 1. バブルの描画プロパティ（色、不透明度、ラベル）を付与
        def get_bubble_style(sector):
            if sector in top5_sectors:
                # トップ5: 濃い赤色、半透明(密集時ヒートマップ化)
                idx = top5_sectors.index(sector)
                number_label = ["①", "②", "③", "④", "⑤"][idx]
                return pd.Series(["crimson", 0.85, number_label, 1.5, "rgba(255,255,255,0.5)"])
            elif sector in worst5_sectors:
                # ワースト5: 鮮やかな青色、くっきり、ラベルなし
                return pd.Series(["royalblue", 1.0, "", 1.5, "rgba(255,255,255,0.5)"])
            else:
                # その他23セクター（ステルス化）
                return pd.Series(["lightgray", 0.15, "", 0, "rgba(0,0,0,0)"])
                
        chart_data[["bubble_color", "bubble_opacity", "display_label", "line_width", "line_color"]] = chart_data["sector"].apply(get_bubble_style)
        
        # ステルスバブルを小さくするためのサイズ調整（全体的な外れ値クリップ適用後、トップ層以外をさらに縮小）
        chart_data['bubble_size'] = chart_data['avg_volume_ratio'].clip(lower=1.0, upper=5.0)
        chart_data.loc[~chart_data['sector'].isin(top5_sectors + worst5_sectors), 'bubble_size'] = 1.0 # ステルスは最小サイズ固定
        
        # 代表銘柄の統合とホバーテキスト
        from utils.constants import REPRESENTATIVE_STOCKS
        chart_data['representative_stocks'] = chart_data['sector'].map(REPRESENTATIVE_STOCKS).fillna('')
        
        chart_data['hover_text'] = chart_data.apply(
            lambda r: (
                f"<b>{r['sector']}</b> ({r['representative_stocks']})<br>"
                f"スコア: {int(r['momentum_score'])}<br>"
                f"PPO: {r['avg_ppo']:+.2f}%<br>"
                f"RSI: {r['avg_rsi']:.1f}<br>"
                f"RVOL: {r['avg_volume_ratio']:.2f}x"
            ), axis=1
        )

        fig_scatter = px.scatter(
            chart_data,
            x="avg_ppo",
            y="avg_rsi",
            size="bubble_size",
            text="display_label",
            hover_name="sector",
            hover_data={"avg_ppo": False, "avg_rsi": False, "bubble_size": False, "sector": False, "display_label": False, "bubble_color": False, "bubble_opacity": False, "line_width": False, "line_color": False, "hover_text": True},
        )

        # Plotly ExpressのデフォルトColorScaleを無効化し、カスタム色と透明度・枠線を各マーカーに直接適用
        fig_scatter.update_traces(
            marker=dict(
                color=chart_data['bubble_color'],
                opacity=chart_data['bubble_opacity'],
                line=dict(width=chart_data['line_width'], color=chart_data['line_color'])
            ),
            textposition='middle center', # 赤バブルのど真ん中に数字を配置
            textfont=dict(size=14, weight="bold", color="white"), # 数字は白抜き
            hovertemplate="%{customdata[0]}<extra></extra>",
            customdata=chart_data[['hover_text']]
        )
        
        # 常に中心（0, 50）が表示されるように軸範囲を調整
        max_abs_ppo = max(abs(chart_data["avg_ppo"].min()), abs(chart_data["avg_ppo"].max()), 1.0)
        max_x = max_abs_ppo * 1.2
        min_x = -max_x
        min_y = -5
        max_y = 105
        
        # 基準線と帯域の追加（X=0, Y=50）
        fig_scatter.add_vline(x=0, line_dash="dash", line_color="rgba(255,255,255,0.2)")
        fig_scatter.add_hline(y=50, line_dash="dash", line_color="rgba(255,255,255,0.2)")
        
        # 「押し目エリア」等の注釈 (背景色がついたので文字はより控えめに、明るく)
        fig_scatter.add_annotation(x=max_x*0.95, y=5, text="安全圏<br>(押し目買いエリア)", showarrow=False, font=dict(color="lightgray", size=13), opacity=0.8, align="right", xanchor="right", yanchor="bottom")
        fig_scatter.add_annotation(x=max_x*0.95, y=95, text="警戒圏<br>(過熱・順張りエリア)", showarrow=False, font=dict(color="lightgray", size=13), opacity=0.8, align="right", xanchor="right", yanchor="top")
        fig_scatter.add_annotation(x=min_x*0.95, y=95, text="撤退圏<br>(戻り売りエリア)", showarrow=False, font=dict(color="lightgray", size=13), opacity=0.8, align="left", xanchor="left", yanchor="top")
        fig_scatter.add_annotation(x=min_x*0.95, y=5, text="氷河期<br>(底値模索エリア)", showarrow=False, font=dict(color="lightgray", size=13), opacity=0.8, align="left", xanchor="left", yanchor="bottom")

        fig_scatter.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=500,
            xaxis_title="トレンドの強さ (PPO %)",
            yaxis_title="短期の加熱感 (RSI)",
            xaxis=dict(range=[min_x, max_x], zeroline=False, gridcolor="rgba(255,255,255,0.05)"),
            yaxis=dict(range=[min_y, max_y], zeroline=False, gridcolor="rgba(255,255,255,0.05)"),
            margin=dict(l=20, r=20, t=30, b=20),
            hovermode="closest",
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

        # === レーダー直下への「凡例（トップ5リスト）」の自動配置 ===
        top5_names = top5_df['sector'].tolist()
        legend_items = []
        numbers = ["①", "②", "③", "④", "⑤"]
        for i, name in enumerate(top5_names):
            legend_items.append(f"{numbers[i]} {name}")
            
        legend_text = " | ".join(legend_items)
        st.markdown(f"""
        <div style='background-color: rgba(220, 20, 60, 0.1); padding: 12px 20px; border-radius: 6px; border-left: 5px solid crimson; margin-top: -15px; margin-bottom: 25px;'>
            <span style='font-size: 1.1em; color: white;'>**🔥 今日の主役 (資金流入トップ5):**</span><br>
            <span style='font-size: 1.05em; color: #e0e0e0; line-height: 1.8; font-weight: bold;'>{legend_text}</span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<hr style='margin:30px 0; border:none; border-top:1px dashed #333;'>", unsafe_allow_html=True)
        
        # --------------------------------------------------
        # Top 5 / Worst 5 チャート (Altair)
        # --------------------------------------------------
        winners = chart_data.head(5).copy()
        losers = chart_data.tail(5).copy()
        losers = losers.sort_values("momentum_score", ascending=True)

        import altair as alt

        col_win, col_lose = st.columns(2)

        with col_win:
            st.markdown("<h4 style='color:#FF4B4B; margin-bottom:10px;'>🔥 資金流入トップ5 (Strong Inflow)</h4>", unsafe_allow_html=True)
            if not winners.empty:
                domain_w = winners["sector"].tolist()
                base_w = alt.Chart(winners).encode(
                    y=alt.Y("sector:N", sort=domain_w, axis=alt.Axis(title=None, labels=False, ticks=False, domain=False))
                )
                
                # スコアを0-100のバーにする
                bars_w = base_w.mark_bar(color="#FF4B4B", cornerRadiusEnd=4, size=24, opacity=0.85).encode(
                    x=alt.X("momentum_score:Q", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(title=None, labels=False, ticks=False, grid=False, domain=False))
                )
                
                # 詳細テキストをバーの右端の外側に配置
                text_w = base_w.mark_text(align="left", dx=4, color="white", font="Inter, sans-serif", fontSize=11).encode(
                    x=alt.X("momentum_score:Q"),
                    text="detail_text:N"
                )
                
                # セクター名テキストをバーの左端(根元)に配置
                label_w = base_w.mark_text(align="left", dx=4, color="white", fontWeight="bold", font="Inter, sans-serif").encode(
                    x=alt.datum(0),
                    text="sector:N"
                )
                
                fig_w = alt.layer(bars_w, text_w, label_w).configure_view(strokeWidth=0).properties(height=200)
                st.altair_chart(fig_w, use_container_width=True)
                
        with col_lose:
            st.markdown("<h4 style='color:#00D26A; margin-bottom:10px;'>🧊 資金流出ワースト5 (Strong Outflow)</h4>", unsafe_allow_html=True)
            if not losers.empty:
                domain_l = losers["sector"].tolist()
                base_l = alt.Chart(losers).encode(
                    y=alt.Y("sector:N", sort=domain_l, axis=alt.Axis(title=None, labels=False, ticks=False, domain=False))
                )
                
                # outflow側は視覚的に反対に伸ばすため元の値を反転させてプロットするアプローチもあるが、
                # 仕様通り「0に近い順」にしてそのままプロットする。バーは短くなる。
                bars_l = base_l.mark_bar(color="#00D26A", cornerRadiusEnd=4, size=24, opacity=0.85).encode(
                    x=alt.X("momentum_score:Q", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(title=None, labels=False, ticks=False, grid=False, domain=False))
                )
                
                text_l = base_l.mark_text(align="left", dx=4, color="white", font="Inter, sans-serif", fontSize=11).encode(
                    x=alt.X("momentum_score:Q"),
                    text="detail_text:N"
                )
                
                label_l = base_l.mark_text(align="left", dx=4, color="white", fontWeight="bold", font="Inter, sans-serif").encode(
                    x=alt.datum(0),
                    text="sector:N"
                )
                
                fig_l = alt.layer(bars_l, text_l, label_l).configure_view(strokeWidth=0).properties(height=200)
                st.altair_chart(fig_l, use_container_width=True)
                
        # --------------------------------------------------
        # 全33業種 詳細データテーブル
        # --------------------------------------------------
        st.markdown("<h4 style='margin-top:20px;'>📋 全33業種 詳細データテーブル</h4>", unsafe_allow_html=True)
        
        with st.expander("💡 テーブルの各項目の見方"):
            st.markdown("""
            * **資金流入スコア**: 4つの指標（騰落率、出来高倍率、25MA乖離率、資金波及度）を加重平均した総合的な資金流入の強さ（0〜100点）。高いほど機関投資家の資金流入が強いと判断できます。
            * **騰落率 (%)**: 前日比の価格変化。セクター全体の現在の勢いを示します。
            * **出来高倍率 (x)**: 過去5日平均に対する本日の出来高ペース（時間補正済）。1.5x以上なら大口の資金流入（本気度が高い）と判断できます。
            * **25MA乖離率 (%)**: 25日移動平均線からの離れ具合。高すぎると高値掴みのリスク（加熱）、マイナスなら下落トレンドを意味します。
            * **資金の波及度 (Breadth)**: セクター内で今日値上がりしている銘柄の割合。ヒートゲージが右に振り切れている（80%以上）ならセクター全体への本物の資金流入（全面高）、逆に短い場合は一部の大型株だけが上がっている「ハリボテ」の可能性があります。
            """)
        
        # 表示用のデータフレーム
        display_df = chart_data[["sector", "representative_stocks", "momentum_score", "avg_percent_change", "avg_volume_ratio", "avg_ppo", "up_down_ratio", "avg_rsi"]].copy()
        
        if "up_down_ratio" in display_df.columns:
            display_df["up_down_ratio"] = display_df["up_down_ratio"] * 100
        
        # 1. 「シグナル」列の自動判定ロジックを作成
        def get_signal(row):
            score = row['momentum_score']
            vol_ratio = row['avg_volume_ratio']
            ppo = row['avg_ppo']
            rsi = row['avg_rsi']
            breadth = row['up_down_ratio'] # 値は 0〜100
            
            # ハリボテ上昇判定（スコアが高いのに波及度が低い）
            if score >= 65 and breadth <= 30:
                return "⚠️ ハリボテ警戒"
            elif vol_ratio >= 1.5 and score >= 70 and breadth >= 80:
                return "🔥 最強の波(全面高)"
            elif vol_ratio >= 1.5 and score >= 70:
                return "🔥 資金流入"
            elif score >= 70 and ppo >= 15:
                return "⚠️ 加熱警戒"
            elif ppo > 0 and pd.notna(rsi) and rsi < 40:
                return "💎 押し目"
            elif ppo < -5 and breadth <= 10:
                return "🧊 総悲観(底打ち待機)"
            elif ppo < -5:
                return "🧊 氷河期"
            return "-"

        display_df['Signal'] = display_df.apply(get_signal, axis=1)
            
        display_df = display_df[["Signal", "sector", "representative_stocks", "momentum_score", "avg_percent_change", "avg_volume_ratio", "avg_ppo", "up_down_ratio"]]
        display_df.columns = ["シグナル", "セクター", "代表銘柄", "資金流入スコア", "騰落率 (%)", "出来高倍率 (x)", "25MA乖離率 (%)", "資金の波及度 (%)"]
        
        # 資金流入スコアで降順
        display_df = display_df.sort_values("資金流入スコア", ascending=False)
        
        with st.expander("⚙️ 表示する列のカスタマイズ（スマホ用）", expanded=False):
            st.markdown("<p style='font-size: 0.9em; color: #b0b0b0; margin-bottom: 5px;'>スマホで表が横にはみ出す場合は、以下のメニューから不要な列を非表示（×）にできます。</p>", unsafe_allow_html=True)
            
            # 表示/非表示を選択するためのマルチセレクトを追加
            all_columns = ["シグナル", "セクター", "代表銘柄", "資金流入スコア", "騰落率 (%)", "出来高倍率 (x)", "25MA乖離率 (%)", "資金の波及度 (%)"]
            
            selected_columns = st.multiselect(
                "表示する列",
                options=all_columns,
                default=all_columns,
                help="選択を外すとその列が表から隠れます。横幅を節約したい時にお使いください。"
            )
            
        if not selected_columns:
            selected_columns = ["セクター", "資金流入スコア"] # すべて消した場合のフェイルセーフ
            
        # ★重要: 順番を元の all_columns の並びに強制する（これがないと、選択した順に列が並んでしまう）
        ordered_selected_columns = [col for col in all_columns if col in selected_columns]
            
        # 選択されたカラムだけでデータフレームを絞り込む
        filtered_df = display_df[ordered_selected_columns]

        # Pandas Styler機能を用いたヒートマップ（背景色）の適用
        def style_dataframe(v):
            return None # dummy

        def highlight_volume(val):
            # 出来高倍率列: 値が 1.5 以上の場合、セルの背景色を「薄い赤色」
            try:
                if float(val) >= 1.5:
                    return 'background-color: rgba(255,75,75,0.2)'
            except:
                pass
            return ''

        def highlight_ppo(val):
            # 25MA乖離率列: 値が 0 未満の場合、セルの背景色を「薄い青色」
            try:
                if float(val) < 0:
                    return 'background-color: rgba(76,155,232,0.2)'
            except:
                pass
            return ''

        # スタイルの適用
        styled_df = filtered_df.style
        if "出来高倍率 (x)" in selected_columns:
            styled_df = styled_df.applymap(highlight_volume, subset=["出来高倍率 (x)"])
        if "25MA乖離率 (%)" in selected_columns:
            styled_df = styled_df.applymap(highlight_ppo, subset=["25MA乖離率 (%)"])
        
        # 2. Streamlit `column_config` を用いたリッチUI化
        st.dataframe(
            styled_df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "シグナル": st.column_config.TextColumn("シグナル", width="medium"),
                "セクター": st.column_config.TextColumn("セクター", width="medium"),
                "代表銘柄": st.column_config.TextColumn(
                    "代表銘柄", 
                    width="medium",
                    help="セクターを代表する主な上場企業"
                ),
                "資金流入スコア": st.column_config.ProgressColumn(
                    "資金流入スコア", 
                    help="4つの指標を加重平均した総合的な資金流入の強さ（0〜100点）。高いほど機関投資家の資金流入が強い。",
                    format="%f",
                    min_value=0,
                    max_value=100,
                ),
                "騰落率 (%)": st.column_config.NumberColumn(
                    "騰落率",
                    help="セクター構成銘柄の前日比の平均。",
                    format="%+.2f %%"
                ),
                "出来高倍率 (x)": st.column_config.NumberColumn(
                    "出来高倍率",
                    help="本日の予測出来高が過去5日平均の何倍か。1.5x以上は機関の介入の可能性大。",
                    format="%.2f x"
                ),
                "25MA乖離率 (%)": st.column_config.NumberColumn(
                    "25MA乖離",
                    help="25日移動平均線からの乖離度合い。トレンドの強さと過熱感を示す。",
                    format="%+.2f %%"
                ),
                "資金の波及度 (%)": st.column_config.ProgressColumn(
                    "資金の波及度 (Breadth)",
                    help="セクター内で今日値上がりしている銘柄の割合。高いほどセクター全体が買われている本物のトレンド。",
                    format="%.0f %%",
                    min_value=0,
                    max_value=100,
                )
            },
            height=600
        )

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<div style='background:rgba(76,155,232,0.1); padding:15px; border-radius:8px; border-left:4px solid #4C9BE8; margin-bottom:20px;'>", unsafe_allow_html=True)
        st.markdown("**🔍 特定のセクターをさらに深掘りする**<br><span style='font-size:0.85rem; color:#ccc;'>「セクター分析」ページに移動して、構成銘柄のリストや出遅れ銘柄を確認できます。</span>", unsafe_allow_html=True)
        
        col_sel, col_btn = st.columns([3, 1])
        with col_sel:
            # ランキング順位を付与して探しやすくする
            sector_list = display_df["セクター"].tolist()
            options = [f"{i+1}位: {sec}" for i, sec in enumerate(sector_list)]
            selected_option = st.selectbox("分析するセクターを選択", options, label_visibility="collapsed")
            target_sector = selected_option.split(": ")[1] if ": " in selected_option else selected_option
            
        with col_btn:
            if st.button("▶ 詳細分析へ", use_container_width=True, type="primary"):
                # st.switch_page は query_params を消してしまうため、session_state を経由して伝達する
                st.session_state["target_sector"] = target_sector
                st.switch_page("pages/sector_analysis.py")
        st.markdown("</div>", unsafe_allow_html=True)

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
