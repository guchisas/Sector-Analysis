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
import yfinance as yf
import time


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

    # 画面上部でのセクター選択（URLパラメータ対応）
    from modules.momentum_calculator import calculate_sector_momentum_scores
    momentum_df = calculate_sector_momentum_scores(latest_date)
    if not momentum_df.empty:
        # 資金流入スコア（momentum_score）の降順でランキング
        momentum_df = momentum_df.sort_values("momentum_score", ascending=False)
        ranked_sectors = momentum_df["sector"].tolist()
        # 最新データにない古いセクターがある場合のフォールバック
        available_sectors = ranked_sectors + [s for s in sector_summary["sector"].unique() if s not in ranked_sectors]
    else:
        available_sectors = sorted(sector_summary["sector"].unique().tolist())
    
    # 遷移時のセクター受け取り（ダッシュボードからのジャンプ用）
    initial_sector = available_sectors[0]
    
    # 1. まずは session_state を優先してチェック
    if "target_sector" in st.session_state:
        if st.session_state["target_sector"] in available_sectors:
            initial_sector = st.session_state["target_sector"]
        # 使用後は削除
        del st.session_state["target_sector"]
        # URLも整合性を合わせる
        try:
            st.query_params["sector"] = initial_sector
        except Exception:
            pass
    else:
        # 2. 次に URLパラメータ をチェック
        try:
            query_params = st.query_params
            if "sector" in query_params and query_params["sector"] in available_sectors:
                initial_sector = query_params["sector"]
        except Exception:
            pass
        
    initial_index = available_sectors.index(initial_sector) if initial_sector in available_sectors else 0

    # 銘柄名からの逆引き検索
    from modules.jpx_stock_list import get_all_listed_stocks
    all_stocks = get_all_listed_stocks()
    if all_stocks:
        with st.expander("🔍 銘柄名・コードからセクターを逆引き検索", expanded=False):
            search_options = ["(銘柄を選んでください)"] + [f"{s['ticker']} {s['name']} ({s['sector']})" for s in all_stocks if s['sector'] in available_sectors]
            selected_search = st.selectbox("検索", search_options, label_visibility="collapsed")
            if selected_search != "(銘柄を選んでください)":
                import re
                m = re.search(r'\((.+?)\)$', selected_search)
                if m:
                    found_sec = m.group(1)
                    st.success(f"✅ その銘柄は **【{found_sec}】** セクターです。")
                    if st.button(f"▶ {found_sec} セクターの分析へジャンプ"):
                        st.query_params["sector"] = found_sec
                        st.rerun()

    st.markdown("### 🎯 セクターを選択")
    
    # プルダウンの選択肢に順位を付与する
    options_with_rank = [f"{i+1}位: {sec}" for i, sec in enumerate(available_sectors)]
    
    selected_option = st.selectbox(
        "詳細を見るセクターを選んでください",
        options_with_rank,
        index=initial_index,
        label_visibility="collapsed"
    )
    
    # "1位: 機械" -> "機械" のように抽出
    selected_sector = selected_option.split(": ")[1] if ": " in selected_option else selected_option
    
    # URLパラメータの更新（他のページから戻ってきた時等のために。Streamlit仕様にあわせて）
    try:
        st.query_params["sector"] = selected_sector
    except Exception:
        pass

    st.markdown("<hr style='margin:10px 0 20px 0; border:none; border-top:1px dashed #333;'>", unsafe_allow_html=True)

    # 選択されたセクターのデータ抽出
    sector_stocks = latest_data[latest_data["sector"] == selected_sector].copy()

    # セクターKPI（全タブ共通で上部に表示）
    if not sector_stocks.empty:
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
    else:
        st.warning(f"「{selected_sector}」セクターの銘柄データがありません。")
        return

    # タブ構成の作成
    tab1, tab2, tab3 = st.tabs(["📋 構成銘柄リスト", "💎 お宝発掘 (ファンダメンタルズ)", "🌐 全33業種との比較"])

    # ==========================================
    # タブ1: 構成銘柄リスト
    # ==========================================
    with tab1:
        st.markdown(f"#### {selected_sector} 主要構成銘柄 ({len(sector_stocks)}銘柄)")
        
        # --- ツリーマップの描画 ---
        st.markdown("##### 🗺️ セクター内マップ (出来高と騰落率)")
        st.caption("ブロックの大きさが「売買代金」、色が「本日の騰落率（赤が下落、緑が上昇）」を表します。")
        tm_df = sector_stocks.copy()
        tm_df["trading_value"] = tm_df["close"] * tm_df["volume"]
        tm_df["percent_change_fmt"] = tm_df["percent_change"].apply(lambda x: f"{x:+.2f}%")
        
        # サイズと色の調整（描画エラー防止）
        tm_df["size_val"] = tm_df["trading_value"].clip(lower=1)
        tm_df["color_val"] = tm_df["percent_change"].clip(lower=-5, upper=5)
        
        fig_tm = px.treemap(
            tm_df,
            path=[px.Constant(selected_sector), "name"],
            values="size_val",
            color="color_val",
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
            custom_data=["ticker", "percent_change_fmt", "volume_ratio"]
        )
        fig_tm.update_traces(
            hovertemplate="<b>%{label}</b><br>コード: %{customdata[0]}<br>騰落率: %{customdata[1]}<br>出来高倍率: %{customdata[2]:.2f}x<extra></extra>",
            textfont=dict(size=14, color="white")
        )
        fig_tm.update_layout(
            height=350, margin=dict(t=10, l=10, r=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            coloraxis_showscale=False
        )
        st.plotly_chart(fig_tm, use_container_width=True)
        
        # --- その他の全銘柄一覧（2段階目）をツリーマップ直下へ移動 ---
        if all_stocks:
            other_stocks = [s for s in all_stocks if s["sector"] == selected_sector and s["ticker"] not in sector_stocks["ticker"].values]
            if other_stocks:
                st.markdown("<br>", unsafe_allow_html=True)
                with st.expander(f"🔽 同じセクター（{selected_sector}）のその他の銘柄 ({len(other_stocks)}件) を表示", expanded=False):
                    st.caption(f"主要銘柄以外で、{selected_sector}に属するスタンダードやグロースなどの全ての銘柄が含まれます。")
                    other_df = pd.DataFrame(other_stocks)[["ticker", "name", "market"]]
                    other_df.columns = ["銘柄コード", "銘柄名", "上場市場"]
                    st.dataframe(other_df, hide_index=True, use_container_width=True)
                    
        st.markdown("<hr style='border:none; border-top:1px dashed #333; margin: 20px 0;'>", unsafe_allow_html=True)
        
        # --- 銘柄カード一覧 ---
        sort_option = st.radio(
            "並び替え",
            ["出来高倍率（高い順）", "RSI（低い順）", "PPO（低い順）"],
            horizontal=True,
        )
        if sort_option == "出来高倍率（高い順）":
            sector_stocks_sorted = sector_stocks.sort_values("volume_ratio", ascending=False)
        elif sort_option == "RSI（低い順）":
            sector_stocks_sorted = sector_stocks.sort_values("rsi", ascending=True)
        else:
            sector_stocks_sorted = sector_stocks.sort_values("ppo", ascending=True)

        for _, row in sector_stocks_sorted.iterrows():
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

    # ==========================================
    # タブ2: お宝出遅れ銘柄発掘
    # ==========================================
    with tab2:
        st.markdown("#### 💎 ファンダ良好・出遅れ銘柄の抽出")
        st.caption("※選んだセクターの「全上場銘柄」から割安な銘柄を探します。取得したデータはデータベースに蓄積され、次回以降ゼロ秒で表示されます。")
        
        sector_avg_pct = sector_summary[sector_summary["sector"] == selected_sector]["avg_percent_change"].values[0] if not sector_summary[sector_summary["sector"] == selected_sector].empty else 0.0
        
        # 全上場銘柄の中から対象セクターのティッカーを特定
        if all_stocks:
            all_sector_stocks = [s for s in all_stocks if s["sector"] == selected_sector]
            all_sector_tickers = [s["ticker"] for s in all_sector_stocks]
            all_stocks_info = {s["ticker"]: {"name": s["name"], "market": s["market"]} for s in all_sector_stocks}
        else:
            all_sector_tickers = sector_stocks["ticker"].tolist()
            all_stocks_info = {row["ticker"]: {"name": row.get("name", ""), "market": ""} for _, row in sector_stocks.iterrows()}

        from modules.db_manager import get_fundamentals, upsert_fundamentals
        from modules.market_data_fetcher import fetch_fundamentals
        
        # --- 1. DBから既存のファンダデータを読み込み ---
        db_funds_df = get_fundamentals(all_sector_tickers)
        db_funds_dict = db_funds_df.set_index("ticker").to_dict("index") if not db_funds_df.empty else {}
        
        # --- 2. 未取得のティッカーを特定 ---
        missing_tickers = [t for t in all_sector_tickers if t not in db_funds_dict]
        
        # メッセージとボタン表示
        if missing_tickers:
            st.info(f"💡 {len(missing_tickers)}件の未取得銘柄（小型株など）があります。検索ボタンを押すと情報を取得してデータベースに蓄積します。")
            search_button_label = "🔍 未取得データを取りに行き、全件からお宝発掘（数十秒）"
        else:
            search_button_label = "⚡ キャッシュデータからお宝発掘（ゼロ秒）"

        if st.button(search_button_label, key=f"btn_search_{selected_sector}", type="primary"):
            fund_data = db_funds_dict.copy()
            
            # 未取得があればAPIで取りに行く
            if missing_tickers:
                with st.spinner(f"未取得の {len(missing_tickers)} 銘柄を裏側で取得中... (徐々にアプリが賢くなります)"):
                    new_funds = fetch_fundamentals(missing_tickers)
                    if new_funds:
                        upsert_fundamentals(new_funds)
                        for item in new_funds:
                            fund_data[item["ticker"]] = item
            
            # --- 3. 出遅れ判定 ---
            top600_dict = sector_stocks.set_index("ticker").to_dict("index")
            laggards = []
            
            for ticker, f_data in fund_data.items():
                per = f_data.get("per")
                pbr = f_data.get("pbr")
                
                # 条件1: 割安 (PBRが1.0未満、またはPERが15未満)
                is_undervalued = (pbr is not None and pbr < 1.0) or (per is not None and 0 < per < 15.0)
                if not is_undervalued:
                    continue
                
                name = all_stocks_info.get(ticker, {}).get("name", "Unknown")
                market = all_stocks_info.get(ticker, {}).get("market", "")
                
                # 条件2: 出遅れ (主要600銘柄ならRSIや騰落率で判定。マイナー銘柄は無条件でリストアップ)
                pct = None
                is_laggard = True
                
                if ticker in top600_dict:
                    t_data = top600_dict[ticker]
                    pct = t_data.get("percent_change", 0.0)
                    rsi = t_data.get("rsi", 50.0)
                    is_laggard = (pct < sector_avg_pct) or (rsi < 50.0)
                
                if is_laggard:
                    laggards.append({
                        "ticker": ticker,
                        "name": name,
                        "market": market,
                        "pct": pct,
                        "pbr": pbr,
                        "per": per,
                        "is_top600": ticker in top600_dict
                    })
            
            # --- 4. 結果の描画 ---
            if laggards:
                st.success(f"🎯 {len(laggards)}件のお宝銘柄・出遅れ銘柄を発見しました！")
                for item in sorted(laggards, key=lambda x: (x["pbr"] or 999)):
                    pbr_str = f"{item['pbr']:.2f}倍" if item['pbr'] is not None else "N/A"
                    per_str = f"{item['per']:.1f}倍" if item['per'] is not None else "N/A"
                    pct_str = f"騰落率: {item['pct']:+.2f}%" if item['pct'] is not None else "騰落率: (マイナー銘柄)"
                    pct_color = '#FF4B4B' if (item['pct'] is not None and item['pct']>0) else '#00D26A'
                    
                    market_badge = f"<span style='font-size:0.75rem; background:#333; padding:2px 6px; border-radius:10px; margin-left:8px; color:#aaa;'>{item['market']}</span>" if item['market'] else ""
                    
                    st.markdown(f"""
                    <div style="background-color:rgba(255,179,71,0.1); border-left:4px solid #FFB347; padding:10px 15px; margin-bottom:10px; border-radius:4px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <div style="font-size:0.9rem; color:#888;">{item['ticker']} {market_badge}</div>
                                <div style="font-size:1.1rem; font-weight:bold;">{item['name']}</div>
                            </div>
                            <div style="text-align:right;">
                                <div style="font-size:1.0rem; color:{pct_color};">{pct_str}</div>
                                <div style="font-size:0.85rem; color:#ccc;">PBR: {pbr_str} | PER: {per_str}</div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("条件に合致するお宝割安銘柄は見つかりませんでした。")

    # ==========================================
    # タブ3: セクター別比較チャート（全体）
    # ==========================================
    with tab3:
        st.markdown("#### 他のセクターとの相対評価")
        st.caption("選択したセクターが、全体33業種の中でどの位置にいるかを把握します。")
        
        # グラフの色塗り関数（選択されたセクターだけ目立たせる）
        def get_highlighted_color(current_sector, is_positive=None, is_ppo=False):
            if current_sector == selected_sector:
                return "rgba(255, 179, 71, 1.0)"  # 強調色（オレンジ）
            
            if is_ppo:
                return "rgba(0, 210, 106, 0.4)" if is_positive else "rgba(255, 75, 75, 0.4)" # 暗め
            else:
                return "rgba(120, 130, 150, 0.4)" # RSI用暗め

        # --- RSIチャート ---
        st.markdown("##### 📊 セクター別 平均RSI")
        chart_data_rsi = sector_summary.sort_values("avg_rsi", ascending=True)
        colors_rsi = [get_highlighted_color(sec) for sec in chart_data_rsi["sector"]]

        fig_rsi = go.Figure(data=[
            go.Bar(
                x=chart_data_rsi["avg_rsi"],
                y=chart_data_rsi["sector"],
                orientation="h",
                marker_color=colors_rsi,
                text=chart_data_rsi["avg_rsi"].round(1),
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>平均RSI: %{x:.1f}<extra></extra>",
            )
        ])
        fig_rsi.add_vline(x=30, line_dash="dash", line_color="#FF4B4B", annotation_text="売られすぎ(30)")
        fig_rsi.add_vline(x=70, line_dash="dash", line_color="#00D26A", annotation_text="買われすぎ(70)")
        fig_rsi.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            height=600, margin=dict(l=120, r=40, t=20, b=20),
            xaxis_title="平均RSI", font=dict(size=11), dragmode=False,
            # 選択されたセクターを目立たせるために目盛りを太くするなどの工夫も可能
        )
        st.plotly_chart(fig_rsi, use_container_width=True, config={"displayModeBar": False})

        # --- PPOチャート ---
        st.markdown("##### 📉 セクター別 PPO（移動平均乖離率）")
        chart_data_ppo = sector_summary.sort_values("avg_ppo", ascending=True)
        colors_ppo = [get_highlighted_color(sec, v >= 0, True) for sec, v in zip(chart_data_ppo["sector"], chart_data_ppo["avg_ppo"])]

        fig_ppo = go.Figure(data=[
            go.Bar(
                x=chart_data_ppo["avg_ppo"],
                y=chart_data_ppo["sector"],
                orientation="h",
                marker_color=colors_ppo,
                text=chart_data_ppo["avg_ppo"].round(2),
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>PPO: %{x:.2f}%<extra></extra>",
            )
        ])
        fig_ppo.add_vline(x=0, line_dash="solid", line_color="rgba(255,255,255,0.4)")
        fig_ppo.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            height=600, margin=dict(l=120, r=40, t=20, b=20),
            xaxis_title="PPO (%)", font=dict(size=11), dragmode=False,
        )
        st.plotly_chart(fig_ppo, use_container_width=True, config={"displayModeBar": False})
