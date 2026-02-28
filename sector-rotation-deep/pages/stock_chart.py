# -*- coding: utf-8 -*-
"""
銘柄チャートページ
- 個別銘柄の価格チャート（ローソク足 + SMAライン）
- テクニカル指標サブチャート
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.db_manager import get_latest_data, get_ticker_history, db_exists
from modules.market_data_fetcher import fetch_batch
from modules.technical_analysis import calculate_all_indicators
from utils.styles import section_header, metric_card, empty_state


def render():
    """銘柄チャートページをレンダリングする"""
    st.markdown("# 📋 銘柄チャート")
    st.caption("個別銘柄のテクニカル分析チャート")

    if not db_exists():
        st.markdown(empty_state(
            "データがありません。ダッシュボードの「データを最新化」ボタンを押してください。", "📭"
        ), unsafe_allow_html=True)
        return

    # 銘柄選択 (フリーワード検索化)
    col_input, col_period = st.columns([2, 1])
    
    with col_input:
        raw_ticker = st.text_input(
            "銘柄ティッカーを入力 (例: 7203, 9984.T)",
            value="7203",
            placeholder="証券コードを入力してください"
        ).strip().upper()
        
    with col_period:
        # 期間選択（デフォルト6mo、分析に必要な75SMA等を確保）
        period = st.radio(
            "表示期間",
            ["3ヶ月", "6ヶ月", "1年"],
            horizontal=True,
            index=1,
        )
        period_map = {"3ヶ月": "3mo", "6ヶ月": "6mo", "1年": "1y"}

    if not raw_ticker:
        return
        
    # 日本株で '.T' が抜けている場合、自動付与（数字のみ、またはアルファベットのみで.Tがない場合を想定。単純にドットが含まれていなければ付与）
    selected_ticker = raw_ticker
    if "." not in selected_ticker and selected_ticker.isalnum():
        selected_ticker += ".T"

    with st.spinner(f"📊 {selected_ticker} のデータをオンデマンド取得中..."):
        try:
            import yfinance as yf
            # API制限対策のため1銘柄のみオンデマンド取得
            df = yf.download(selected_ticker, period=period_map[period], progress=False)
        except Exception as e:
            st.error(f"データの取得に失敗しました。ティッカーが正しいか確認してください。（エラー: {e}）")
            return

    if df.empty:
        st.error(f"❌ {selected_ticker} のデータを取得できませんでした。上場廃止やティッカー間違いの可能性があります。")
        return

    # MultiIndexカラムの場合は第1階層（Open, High, Low, Close, Volume）だけを取得する
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    elif "Close" not in df.columns and "close" in [c.lower() for c in df.columns]:
        # yfinanceのバージョンによる違い吸収
        df.rename(columns={c: c.capitalize() for c in df.columns}, inplace=True)
    
    # 欠損値があれば前日終値などで埋める
    df = df.ffill().bfill()

    # テクニカル指標計算
    df = calculate_all_indicators(df)

    # 最新データ表示
    last = df.iloc[-1]
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        close_val = last.get("Close", 0)
        st.markdown(metric_card("終値", f"¥{close_val:,.0f}", "💹"), unsafe_allow_html=True)
    with col2:
        rsi_val = last.get("rsi", 0)
        rsi_icon = "🔴" if rsi_val and rsi_val <= 30 else ("🟢" if rsi_val and rsi_val >= 70 else "🔵")
        st.markdown(metric_card("RSI(14)", f"{rsi_val:.1f}" if pd.notna(rsi_val) else "N/A", rsi_icon), unsafe_allow_html=True)
    with col3:
        vr_val = last.get("volume_ratio", 0)
        st.markdown(metric_card("出来高倍率", f"{vr_val:.2f}x" if pd.notna(vr_val) else "N/A", "📊"), unsafe_allow_html=True)
    with col4:
        ppo_val = last.get("ppo", 0)
        st.markdown(metric_card("PPO", f"{ppo_val:.2f}%" if pd.notna(ppo_val) else "N/A", "📈"), unsafe_allow_html=True)

    # ===== ローソク足チャート + SMA =====
    st.markdown(section_header(f"{selected_ticker} 価格チャート", "📈"), unsafe_allow_html=True)

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=("価格 & 移動平均線", "出来高", "RSI"),
    )

    # ローソク足
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="価格",
            increasing_line_color="#00D26A",
            decreasing_line_color="#FF4B4B",
        ),
        row=1, col=1,
    )

    # SMAライン
    for sma_col, color, name in [
        ("sma5", "#FFD700", "SMA5"),
        ("sma25", "#4C9BE8", "SMA25"),
        ("sma75", "#FF6B9D", "SMA75"),
    ]:
        if sma_col in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=df[sma_col],
                    name=name, line=dict(color=color, width=1.5),
                    opacity=0.8,
                ),
                row=1, col=1,
            )

    # 出来高バー
    if "Volume" in df.columns:
        vol_colors = ["#00D26A" if c >= o else "#FF4B4B"
                      for c, o in zip(df["Close"], df["Open"])]
        fig.add_trace(
            go.Bar(
                x=df.index, y=df["Volume"],
                name="出来高",
                marker_color=vol_colors,
                opacity=0.7,
            ),
            row=2, col=1,
        )

    # RSI
    if "rsi" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df["rsi"],
                name="RSI(14)",
                line=dict(color="#4C9BE8", width=1.5),
            ),
            row=3, col=1,
        )
        # RSI基準線
        fig.add_hline(y=70, line_dash="dash", line_color="#00D26A", row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="#FF4B4B", row=3, col=1)

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=700,
        margin=dict(l=20, r=20, t=40, b=20),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_rangeslider_visible=False,
        font=dict(size=11),
        dragmode=False,  # スワイプでのズーム・パンを無効化
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)")

    st.plotly_chart(fig, use_container_width=True, config={
        "scrollZoom": False,
        "displayModeBar": False,
    })
    
    # ===== AIアナリスト（参考ちゃん）分析パネル =====
    st.markdown("<hr style='margin:40px 0; border:none; border-top:1px dashed #333;'>", unsafe_allow_html=True)
    st.markdown("### 🦜👓 参考ちゃん先生のスイング分析")
    
    # トレードロジックのFACT計算
    try:
        current_close = float(df["Close"].iloc[-1])
        current_vol = float(df["Volume"].iloc[-1])
        
        # Phase 1: 落ちるナイフ
        sma25_current = float(df["sma25"].iloc[-1]) if pd.notna(df["sma25"].iloc[-1]) else 0
        sma75_current = float(df["sma75"].iloc[-1]) if pd.notna(df["sma75"].iloc[-1]) else 0
        is_falling_knife = bool((current_close < sma25_current) and (sma25_current < sma75_current))
        
        # Phase 3: 簡易Pivot（ブレイクアウト）
        recent_40d = df.tail(40)
        pivot_40d_high = float(recent_40d["High"].max())
        
        recent_20d = df.tail(20)
        avg_vol_20d = float(recent_20d["Volume"].mean())
        
        is_breakout = bool((current_close > pivot_40d_high) and (current_vol > avg_vol_20d))
        
        # Phase 4: リスク・リワード算出
        stop_loss_20d_low = float(recent_20d["Low"].min())
        
        if current_close > pivot_40d_high:
            # 既に直近高値超えの場合は、現在地から+10%を仮置き
            target_price = current_close * 1.10
        else:
            target_price = pivot_40d_high
            
        risk = current_close - stop_loss_20d_low
        reward = target_price - current_close
        
        if risk > 0:
            rr_ratio = reward / risk
        else:
            rr_ratio = 99.9 # 分母ゼロ回避
            
        technical_facts = {
            "current_close": current_close,
            "sma25": sma25_current,
            "sma75": sma75_current,
            "is_falling_knife": is_falling_knife,
            "pivot_40d": pivot_40d_high,
            "is_breakout": is_breakout,
            "20d_avg_volume": avg_vol_20d,
            "current_volume": current_vol,
            "stop_loss": stop_loss_20d_low,
            "target": target_price,
            "rr_ratio": rr_ratio
        }
        
        from modules.ai_analyzer import analyze_swing_trade_with_gemini
        
        # 分析実行ボタン（API制限回避のオンデマンド）
        if st.button("✨ 参考ちゃん先生に分析を依頼する", type="primary"):
            with st.spinner("思考中...（事実に基づく戦略を構築しています）"):
                ai_report = analyze_swing_trade_with_gemini(selected_ticker, technical_facts)
                
            st.markdown(f"""
            <div style="background-color:rgba(30,40,50,0.8); border-top:4px solid #4C9BE8; padding:20px; border-radius:8px; margin-top:20px;">
                {ai_report}
            </div>
            """, unsafe_allow_html=True)
            
    except Exception as e:
        st.warning(f"分析に必要なデータが不足しているか、エラーが発生しました: {e}")
