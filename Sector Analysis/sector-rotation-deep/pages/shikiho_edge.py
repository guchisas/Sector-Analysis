# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import datetime
import time
import os
import plotly.express as px
from modules import db_manager, market_data_fetcher, technical_analysis

def get_elapsed_market_minutes():
    """本日の東証の経過営業時間を算出する（9:00-11:30, 12:30-15:00）"""
    now = datetime.datetime.now()
    if now.weekday() >= 5: return 300
    if now.hour < 9: return 0
    if now.hour >= 15: return 300
    
    elapsed = (now.hour - 9) * 60 + now.minute
    if elapsed > 150: # 11:30 以降
        if elapsed < 210: # 12:30 前 (昼休み)
            elapsed = 150
        else: # 12:30 以降
            elapsed -= 60
    return elapsed

def is_market_open():
    now = datetime.datetime.now()
    if now.weekday() >= 5: return False
    if now.hour < 9 or now.hour >= 15: return False
    if now.hour == 11 and now.minute >= 30: return False
    if now.hour == 12 and now.minute < 30: return False
    return True

FETCH_TIME_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "shikiho_last_fetch.txt")

def get_last_fetch_datetime():
    if os.path.exists(FETCH_TIME_FILE):
        try:
            with open(FETCH_TIME_FILE, "r") as f:
                return datetime.datetime.fromisoformat(f.read().strip())
        except Exception:
            pass
    return datetime.datetime.min

def save_last_fetch_datetime():
    with open(FETCH_TIME_FILE, "w") as f:
        f.write(datetime.datetime.now().isoformat())

# データをキャッシュし、UIリロード時に計算し直さないようにする
@st.cache_data
def load_shikiho_and_market_data(force_refresh=False):
    # 1. DBから四季報ファンダメンタルズを取得
    shikiho_df = db_manager.get_shikiho_data()
    if shikiho_df.empty:
        return pd.DataFrame()

    tickers = shikiho_df["code"].tolist()
    
    # 2. force_refresh が True なら yfinance から直接取得して計算・保存
    if force_refresh:
        # PPOや75SMAを計算するため、過去6ヶ月分(約120営業日)のデータを取得
        market_data_dict = market_data_fetcher.fetch_all_stocks(tickers, period="6mo")
        
        market_open = is_market_open()
        elapsed_min = get_elapsed_market_minutes()
        
        results = []
        for code in tickers:
            if code in market_data_dict and not market_data_dict[code].empty:
                df_history = market_data_dict[code]
                signals = technical_analysis.calculate_advanced_signals(df_history, is_market_open=market_open, elapsed_minutes=elapsed_min)
                if signals:
                    signals["code"] = code
                    results.append(signals)
                    
        if results:
            df_signals = pd.DataFrame(results)
            # マージ
            merged_df = pd.merge(shikiho_df, df_signals, on="code", how="inner")
            return merged_df
            
    # キャッシュがない場合 or DBのみから復元する場合の簡易対応（通常はforce_refresh=Trueで呼ばれる想定）
    # 今回はオンデマンド取得を必須とするため、ここでは空を返すか、前回のキャッシュを利用する
    return pd.DataFrame()

def render():
    st.markdown("## 🎯 四季報・最強銘柄スナイパー")
    
    # DBからファンダ情報を取得して状態を確認
    shikiho_df = db_manager.get_shikiho_data()
    if shikiho_df.empty:
        st.warning("四季報データが登録されていません。`data/` フォルダにあるCSVのインポート処理を確認してください。")
        return
        
    csv_updated_at_str = shikiho_df["csv_updated_at"].iloc[0]
    csv_updated_at = datetime.datetime.strptime(csv_updated_at_str, "%Y-%m-%d %H:%M:%S")
    days_since_update = (datetime.datetime.now() - csv_updated_at).days
    
    if days_since_update >= 90:
        st.error(f"⚠️ **データの鮮度警告**: 四季報CSVデータが前回更新から {days_since_update}日 経過しています。次号四季報の最新データに更新することを推奨します。")

    # --- 0. コントロールパネル ---
    last_fetch = get_last_fetch_datetime()
    time_since_last_fetch = (datetime.datetime.now() - last_fetch).total_seconds() / 60.0
    
    col1, col2 = st.columns([3, 1])
    with col1:
        if last_fetch > datetime.datetime.min:
            st.caption(f"最終データ取得: {last_fetch.strftime('%Y-%m-%d %H:%M:%S')} (現在 {int(time_since_last_fetch)}分 経過)")
        else:
            st.caption("データがまだ取得されていません。「最新データを取得」を押してください。")
            
    with col2:
        btn_disabled = time_since_last_fetch < 15
        if st.button("🔄 最新データを取得", disabled=btn_disabled, use_container_width=True):
            with st.spinner("データを取得・解析中..."):
                st.session_state["shikiho_df"] = load_shikiho_and_market_data(force_refresh=True)
                save_last_fetch_datetime()
            st.rerun()

    # セッションステートにデータがなければ初期表示を促す
    if "shikiho_df" not in st.session_state or st.session_state["shikiho_df"].empty:
        if last_fetch > datetime.datetime.min:
            # キャッシュからロード試行
            with st.spinner("データをロード中..."):
                st.session_state["shikiho_df"] = load_shikiho_and_market_data(force_refresh=True)
                st.rerun()
        else:
            st.info("👆 上の「最新データを取得」ボタンを押して、スナイパー分析を開始してください。")
            return

    df = st.session_state["shikiho_df"].copy()
    if df.empty:
        st.error("データの取得に失敗しました。")
        return

    # --- 1. アクション・ターゲット（ヘッドライン） ---
    st.markdown("### 🎯 アクション・ターゲット")
    
    # 優先順位: 0=極上押し目, 1=資金流入初動
    targets_df = df[df["signal_priority"].isin([0, 1])].copy()
    targets_df = targets_df.sort_values(["signal_priority", "rr_ratio"], ascending=[True, False])

    if targets_df.empty:
        st.info("現在、シグナルが点灯している銘柄はありません。")
    else:
        # 上位3銘柄をカード表示
        cols = st.columns(min(3, len(targets_df)))
        for i, (_, row) in enumerate(targets_df.head(3).iterrows()):
            with cols[i]:
                # CSSスタイリング
                border_color = "#39ff14" if row["signal_priority"] == 0 else "#ff4500"
                bg_color = "rgba(57, 255, 20, 0.05)" if row["signal_priority"] == 0 else "rgba(255, 69, 0, 0.05)"
                st.markdown(f"""
                <div style="border: 2px solid {border_color}; border-radius: 8px; padding: 15px; background-color: {bg_color}; height: 100%;">
                    <div style="font-size: 1.2rem; font-weight: bold; margin-bottom: 5px;">
                        {row['signal_icon']} {row['name']} <span style="font-size: 0.9em; color: gray;">({row['code'].replace('.T', '')})</span>
                    </div>
                    <div style="font-size: 0.9em; margin-bottom: 10px;"><b>{row['signal_type']}</b></div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.85em; margin-bottom: 5px;">
                        <span>RSI: {row['rsi']}</span>
                        <span>RVOL: {row['rvol']}x</span>
                    </div>
                    <div style="font-size: 0.9em; font-weight: bold; margin-bottom: 15px;">推定 R:R = {row['rr_ratio']}</div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander("詳細と選定理由"):
                    st.write(f"**【診断士の選定理由】**\n{row['reason']}")
                    
                    # AI講評ボタン
                    ai_btn_key = f"ai_btn_{row['code']}"
                    ai_res_key = f"ai_res_{row['code']}"
                    
                    if st.button(f"🤖 参考ちゃんに講評を聞く", key=ai_btn_key):
                        with st.spinner("AIが分析中..."):
                            from modules import ai_analyzer
                            import json
                            fact_data = {
                                "コード": row["code"],
                                "銘柄名": row["name"],
                                "シグナル種別": row["signal_type"],
                                "RSI": row["rsi"],
                                "RVOL": row["rvol"],
                                "推定R:R": row["rr_ratio"],
                                "選定理由": row["reason"]
                            }
                            prompt = f"""
                            以下の定性データとテクニカル指標のファクトに基づいて、この銘柄の現状に対する辛口のスクリーニング講評を行ってください。

                            【システムルール（厳守）】
                            1. テクニカル指標と「選定理由」の紐付けのみを行うこと。
                            2. 信用残高や直近の機関の空売り動向など、提供されていないデータ（需給動向など）については絶対に推測せず、「判断不能である」と明記すること。
                            3. 未来の株価予測や「買い推奨」「売り推奨」は絶対に行わないこと。
                            4. 短く、簡潔に、しかし鋭い洞察を提供すること。

                            【ファクトデータ】
                            {json.dumps(fact_data, ensure_ascii=False, indent=2)}
                            """
                            response = ai_analyzer.call_gemini_api(prompt)
                            st.session_state[ai_res_key] = response
                            
                    if ai_res_key in st.session_state:
                        st.info(st.session_state[ai_res_key])
                        
        if len(targets_df) > 3:
            st.caption(f"🔽 他 {len(targets_df) - 3} 銘柄がシグナル点灯中（詳細は下部テーブル参照）")

    st.markdown("---")
    
    # --- 2. ファンダ×テクニカル スナイパー散布図 (Plotly) ---
    st.markdown("### 🔭 スナイパー散布図")
    
    # グラフ用データ整形
    plot_df = df.copy()
    plot_df["rvol_size"] = plot_df["rvol"].clip(lower=0.5, upper=5.0) # サイズ調整用
    
    # Y軸（営業益成長率）の動的クリッピング (IQR)
    q1 = plot_df["op_profit_growth"].quantile(0.25)
    q3 = plot_df["op_profit_growth"].quantile(0.75)
    iqr = q3 - q1
    y_min = q1 - 1.5 * iqr
    y_max = q3 + 1.5 * iqr
    
    fig = px.scatter(
        plot_df,
        x="rsi",
        y="op_profit_growth",
        size="rvol_size",
        color="signal_type",
        color_discrete_map={
            "極上押し目": "#39ff14", # ネオングリーン
            "資金流入初動": "#ff4500", # オレンジレッド
            "注目・打診候補": "#00BFFF", # ディープスカイブルー
            "観察継続": "#888888",
            "監視外": "#333333"
        },
        hover_name="name",
        hover_data={
            "code": True,
            "rsi": True,
            "op_profit_growth": True,
            "rvol": True,
            "rr_ratio": True,
            "signal_type": True,
            "signal_reason": True,
            "rvol_size": False,
        },
        title="RSI × 営業益成長率 (バブルサイズ: 予測出来高倍率 RVOL)",
        range_y=[y_min, y_max], # 外れ値カット
    )
    
    # UIをステルス（暗色基調）に調整
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white"),
        xaxis=dict(title="RSI(14) ← 売られすぎ | 買われすぎ →", gridcolor="#333", zerolinecolor="#555"),
        yaxis=dict(title="営業益成長率 (%)", gridcolor="#333", zerolinecolor="#555"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    # R:Rと選定理由をホバーに押し込むのはPlotly Expressだと少し工夫が必要なため、
    # カスタムテンプレート（hovertemplate）で上書きする
    fig.update_traces(
        hovertemplate="<b>%{hovertext}</b><br><br>RSI: %{x}<br>営業益成長率: %{y}%<br>RVOL: %{customdata[3]}<br>R:R: %{customdata[4]}<br>シグナル: %{customdata[5]}<br>理由: %{customdata[6]}"
    )
    
    st.plotly_chart(fig, use_container_width=True)

    # --- 3. トップ50 リアルタイム・ステータスボード ---
    st.markdown("### 📋 リアルタイム・ステータスボード")
    
    # 表示用データフレームの整形
    display_df = df.copy()
    display_df = display_df.sort_values(["signal_priority", "rr_ratio"], ascending=[True, False])
    
    # 必要なカラムに絞る
    display_cols = ["signal_icon", "code", "name", "price", "percent_change", "rsi", "rvol", "rr_ratio", "op_profit_growth", "signal_type", "signal_reason"]
    display_df = display_df[display_cols]
    
    # 列名リネーム
    display_df = display_df.rename(columns={
        "signal_icon": "標",
        "code": "コード",
        "name": "銘柄名",
        "price": "現在値",
        "percent_change": "前日比(%)",
        "rsi": "RSI",
        "rvol": "RVOL",
        "rr_ratio": "R:R",
        "op_profit_growth": "営業益成長率(%)",
        "signal_type": "シグナル",
        "signal_reason": "判定理由"
    })
    
    # CSSスタイリングを通じた監視外のグレーアウトと少数点フォーマット処理
    def style_dataframe(row):
        if row["シグナル"] == "監視外":
            return ["color: #444444; background-color: transparent;"] * len(row)
        elif row["シグナル"] == "極上押し目":
            return ["background-color: rgba(57, 255, 20, 0.1);"] * len(row)
        elif row["シグナル"] == "資金流入初動":
            return ["background-color: rgba(255, 69, 0, 0.1);"] * len(row)
        elif row["シグナル"] == "注目・打診候補":
            return ["background-color: rgba(0, 191, 255, 0.1);"] * len(row)
        else:
            return [""] * len(row)

    styled_df = display_df.style.apply(style_dataframe, axis=1)
    
    # 数値フォーマットの適用（見やすく少数点を丸める）
    format_dict = {
        "現在値": "{:,.0f}",
        "前日比(%)": "{:+.2f}",
        "RSI": "{:.1f}",
        "RVOL": "{:.2f}",
        "R:R": "{:.2f}",
        "営業益成長率(%)": "{:.1f}",
    }
    styled_df = styled_df.format(format_dict, na_rep="-")
    
    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
        height=600
    )
