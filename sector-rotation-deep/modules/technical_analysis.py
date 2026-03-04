# -*- coding: utf-8 -*-
"""
テクニカル指標計算モジュール
- SMA(5, 25, 75)
- PPO (移動平均乖離率)
- RSI(14)
- 出来高急増率
"""

import pandas as pd
import numpy as np


def calculate_sma(series: pd.Series, window: int) -> pd.Series:
    """単純移動平均線（SMA）を計算する"""
    return series.rolling(window=window, min_periods=1).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI（Relative Strength Index）を計算する"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    # Wilderの移動平均（指数移動平均）
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_ppo(sma_short: pd.Series, sma_long: pd.Series) -> pd.Series:
    """
    PPO（移動平均乖離率）を計算する
    PPO = (SMA5 - SMA25) / SMA25 * 100
    """
    return ((sma_short - sma_long) / sma_long * 100).replace([np.inf, -np.inf], np.nan)


def calculate_volume_ratio(volume: pd.Series, window: int = 5) -> pd.Series:
    """
    出来高急増率を計算する
    当日出来高 / 過去5日平均出来高（当日を含まない）
    """
    # shift(1) で当日を除外し、過去5日間の平均と比較する
    avg_volume = volume.rolling(window=window, min_periods=1).mean().shift(1)
    ratio = (volume / avg_volume).replace([np.inf, -np.inf], np.nan)
    return ratio


def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    全テクニカル指標を一括計算する

    Args:
        df: 'Close'と'Volume'カラムを持つDataFrame（日付でソート済み）

    Returns:
        指標カラムが追加されたDataFrame
    """
    if df.empty or "Close" not in df.columns:
        return df

    result = df.copy()

    # SMA計算
    result["sma5"] = calculate_sma(result["Close"], 5)
    result["sma25"] = calculate_sma(result["Close"], 25)
    result["sma75"] = calculate_sma(result["Close"], 75)

    # PPO計算
    result["ppo"] = calculate_ppo(result["sma5"], result["sma25"])

    # RSI計算
    result["rsi"] = calculate_rsi(result["Close"], 14)

    # 出来高急増率計算
    if "Volume" in result.columns:
        result["volume_ratio"] = calculate_volume_ratio(result["Volume"], 5)
    else:
        result["volume_ratio"] = np.nan

    return result


def get_latest_indicators(df: pd.DataFrame) -> dict:
    """
    最新日の指標値を辞書で返す

    Returns:
        {"close": ..., "volume": ..., "rsi": ..., "sma5": ..., "sma25": ...,
         "sma75": ..., "ppo": ..., "volume_ratio": ...}
    """
    if df.empty:
        return {}

    calculated = calculate_all_indicators(df)
    if calculated.empty:
        return {}

    last_row = calculated.iloc[-1]
    
    # 前日比 (percent_change) を計算
    percent_change = 0.0
    if len(calculated) >= 2:
        prev_row = calculated.iloc[-2]
        if pd.notna(prev_row.get("Close")) and prev_row["Close"] > 0:
            percent_change = (last_row.get("Close", 0) - prev_row["Close"]) / prev_row["Close"] * 100

    return {
        "date": str(last_row.name.date()) if hasattr(last_row.name, "date") else str(last_row.name),
        "open": float(last_row.get("Open", 0)) if pd.notna(last_row.get("Open")) else None,
        "high": float(last_row.get("High", 0)) if pd.notna(last_row.get("High")) else None,
        "low": float(last_row.get("Low", 0)) if pd.notna(last_row.get("Low")) else None,
        "close": float(last_row.get("Close", 0)) if pd.notna(last_row.get("Close")) else None,
        "volume": int(last_row.get("Volume", 0)) if pd.notna(last_row.get("Volume")) else None,
        "rsi": round(float(last_row.get("rsi", 0)), 2) if pd.notna(last_row.get("rsi")) else None,
        "sma5": round(float(last_row.get("sma5", 0)), 2) if pd.notna(last_row.get("sma5")) else None,
        "sma25": round(float(last_row.get("sma25", 0)), 2) if pd.notna(last_row.get("sma25")) else None,
        "sma75": round(float(last_row.get("sma75", 0)), 2) if pd.notna(last_row.get("sma75")) else None,
        "ppo": round(float(last_row.get("ppo", 0)), 2) if pd.notna(last_row.get("ppo")) else None,
        "volume_ratio": round(float(last_row.get("volume_ratio", 0)), 2) if pd.notna(last_row.get("volume_ratio")) else None,
        "percent_change": round(float(percent_change), 2),
    }

# =========================================================================
# 四季報スナイパー・ダッシュボード専用: 高度なシグナル計算ロジック
# =========================================================================

def _calculate_rvol(volume: int, avg_volume_20d: float, is_market_open: bool = False, elapsed_minutes: int = 0) -> float:
    """
    RVOL (予測出来高倍率) を計算する。
    - 市場稼働中: 経過時間を考慮して本日の最終的な出来高を予測した上での倍率
    - 市場終了後/休場: 本日の確定出来高と過去20日平均の倍率
    """
    if avg_volume_20d <= 0:
        return 0.0
        
    if is_market_open and elapsed_minutes > 0:
        # 東京証券取引所の営業時間は通常 9:00-11:30、12:30-15:00 の合計300分
        # ただし昼休みを跨ぐ特殊な処理が必要になるため、簡易的に総取引時間を300分として算出
        market_total_minutes = 300
        # 経過時間が300分を超えている（引け後）場合は確定値として扱う
        if elapsed_minutes >= market_total_minutes:
            predicted_volume = volume
        else:
            predicted_volume = volume * (market_total_minutes / elapsed_minutes)
        return float(predicted_volume / avg_volume_20d)
    else:
        return float(volume / avg_volume_20d)

def _calculate_rr_ratio(current_price: float, min_60d: float, max_60d: float, sma75: float) -> float:
    """
    R:R (リスクリワード) を計算する
    [ (直近60日の最高値 または 75SMA のうち低い方) - 現在値 ] / [ 現在値 - 直近60日の最安値 ]
    """
    if current_price <= min_60d:
        return 99.9  # リスクがほぼ無い（底値）状態の便宜上の最大値
        
    target_high = min(max_60d, sma75) if pd.notna(sma75) and sma75 > 0 else max_60d
    reward = target_high - current_price
    risk = current_price - min_60d
    
    if risk <= 0:
        return 99.9
        
    return float(reward / risk)

def calculate_advanced_signals(df: pd.DataFrame, is_market_open: bool = False, elapsed_minutes: int = 0) -> dict:
    """
    四季報トップ50専用のシグナル判定を行う
    
    Args:
        df: 日付でソート済みのDataFrame (最低60日分のデータが必要)
    Returns:
        シグナル情報を含む辞書
    """
    if df.empty or len(df) < 20: # 過去20日平均が取れない場合は空
        return {}
        
    # 基本のテクニカル指標を計算
    calc_df = calculate_all_indicators(df)
    current = calc_df.iloc[-1]
    
    # 過去データから必要な数値を抽出
    last_60d = calc_df.tail(60)
    last_20d = calc_df.tail(20) # 昨日は含めないため正しくは tail(21).head(20) だが近似
    last_3d = calc_df.tail(3)
    
    # 当日を除いた過去20日平均出来高
    if len(calc_df) >= 21:
        avg_vol_20d = calc_df["Volume"].iloc[-21:-1].mean()
    else:
        avg_vol_20d = calc_df["Volume"].iloc[:-1].mean()
        
    # 当日を除いた過去3日平均出来高（売り枯れ判定用）
    if len(calc_df) >= 4:
        avg_vol_3d = calc_df["Volume"].iloc[-4:-1].mean()
    else:
        avg_vol_3d = avg_vol_20d

    min_60d = last_60d["Low"].min()
    max_60d = last_60d["High"].max()
    
    current_price = current["Close"]
    sma25 = current["sma25"]
    sma75 = current["sma75"]
    rsi = current["rsi"]
    volume = current["Volume"]
    
    # 前日比
    prev_close = calc_df["Close"].iloc[-2]
    percent_change = ((current_price - prev_close) / prev_close) * 100
    
    # RVOL & R:R 計算
    rvol = _calculate_rvol(volume, avg_vol_20d, is_market_open, elapsed_minutes)
    rr_ratio = _calculate_rr_ratio(current_price, min_60d, max_60d, sma75)
    
    # ---------------------------------------------------------
    # シグナル判定ロジック
    # ---------------------------------------------------------
    signal_type = "観察継続" # デフォルト
    signal_icon = "👀"
    signal_priority = 3 # 優先順位: 0=極上押し目, 1=資金流入初動, 2=注目・打診, 3=観察継続, 4=監視外
    signal_reason = "シグナル点灯条件を満たしていないため待機中"
    
    # ⚠️ 監視外（落ちるナイフの強制ブロック）
    if current_price < sma25 and sma25 < sma75:
        signal_type = "監視外"
        signal_icon = "⚠️"
        signal_priority = 4
        signal_reason = "現在値が中期・長期より下（ダウントレンド）のため"
    else:
        # 💎 極上押し目（反発狙い）
        if pd.notna(rsi) and rsi <= 35:
            # 売り枯れ確認（直近3日の平均出来高が20日平均を下回る）
            if avg_vol_3d < avg_vol_20d:
                signal_type = "極上押し目"
                signal_icon = "💎"
                signal_priority = 0
                signal_reason = "RSI 35以下 ＆ 出来高減少（売り枯れ）が見られるため"
                
        # 🔥 資金流入初動（モメンタム・ブレイク）
        elif rvol >= 2.0 and pd.notna(rsi) and rsi < 70 and percent_change > 0:
            signal_type = "資金流入初動"
            signal_icon = "🔥"
            signal_priority = 1
            signal_reason = f"出来高急増（{round(rvol, 1)}倍）＆ 株価の反発が見られるため"
        
        # 🌟 注目・打診候補（観察継続の中でも良好なもの）
        elif pd.notna(rsi) and pd.notna(rr_ratio):
            if rr_ratio >= 1.0 or rsi <= 45:
                signal_type = "注目・打診候補"
                signal_icon = "🌟"
                signal_priority = 2
                signal_reason = "リスクリワード良好（1.0以上）またはRSI 45以下で割安圏のため"

    return {
        "price": float(current_price),
        "percent_change": round(float(percent_change), 2),
        "rsi": round(float(rsi), 1) if pd.notna(rsi) else None,
        "rvol": round(float(rvol), 2),
        "rr_ratio": round(float(rr_ratio), 2),
        "signal_type": signal_type,
        "signal_icon": signal_icon,
        "signal_priority": signal_priority,
        "signal_reason": signal_reason
    }
