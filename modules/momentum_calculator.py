# -*- coding: utf-8 -*-
"""
セクターモメンタムスコア計算モジュール
4つの要素（Zスコア、RVOL、25MA乖離率、騰落レシオ）に基づき、
各セクターの資金流入度合いを示す「総合スコア（0〜100）」を算出する。
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

def calculate_estimated_volume_ratio(current_volume: int, avg_volume_5d: float, current_time: datetime = None) -> float:
    """
    日本の株式市場(9:00-15:00)におけるU字カーブ（スマイルカーブ）を考慮し、
    現在の出来高から本日の「予測総出来高」を算出し、過去5日平均に対する倍率（RVOL）を返す。
    
    Args:
        current_volume: 現在の総出来高
        avg_volume_5d: 過去5日間の平均出来高
        current_time: 現在時刻（省略時は現在システム時刻）
        
    Returns:
        RVOL（出来高倍率）
    """
    if avg_volume_5d <= 0 or pd.isna(avg_volume_5d):
        return 0.0
        
    if current_time is None:
        # タイムゾーンをJSTとして取得
        jst = timezone(timedelta(hours=9))
        current_time = datetime.now(jst)
        
    # 現在時刻が9:00〜15:00の間か判定
    h = current_time.hour
    m = current_time.minute
    
    # 営業時間外（15:00以降または9:00前など）は、すでに引け（r=1.0）として単純計算
    if h >= 15 or h < 9:
        return current_volume / avg_volume_5d
        
    # 経過時間（分）の計算 (9:00起点)
    # 昼休み（11:30 - 12:30）は除外する
    t = 0
    
    if h == 9:
        t = m
    elif h == 10:
        t = 60 + m
    elif h == 11:
        if m <= 30:
            t = 120 + m
        else:
            t = 150 # 11:30以降は150分で固定（昼休み中）
    elif h == 12:
        if m >= 30:
            t = 150 + (m - 30)
        else:
            t = 150 # 昼休み中
    elif h == 13:
        t = 150 + 30 + m
    elif h == 14:
        t = 150 + 90 + m
        
    # 累積出来高消化率 (r) の計算モデル
    if t <= 0:
        # 開始直後などで t=0 の場合、0割りを防ぐ
        return 0.0
    elif t <= 30:
        # 9:00-9:30: 最初の30分で25%消化
        r = (t / 30.0) * 0.25
    elif t <= 150:
        # 9:30-11:30: 120分で20%消化
        r = 0.25 + ((t - 30.0) / 120.0) * 0.20
    elif t <= 270:
        # 12:30-14:30: 120分で25%消化
        r = 0.45 + ((t - 150.0) / 120.0) * 0.25
    else:
        # 14:30-15:00: 最後の30分で30%消化
        r = 0.70 + ((t - 270.0) / 30.0) * 0.30
        
    # 予測総出来高 = 現在の出来高 / 消化率
    predicted_volume = current_volume / r
    
    # RVOL = 予測出来高 / 5日平均出来高
    rvol = predicted_volume / avg_volume_5d
    
    return rvol


def calculate_z_score(current_val: float, history_vals: pd.Series) -> float:
    """
    過去の履歴データ（シリーズ）に基づいて、現在の値のZスコアを計算する。
    Z = (現在値 - 平均) / 標準偏差
    """
    if len(history_vals) < 2:
        return 0.0
        
    mean = history_vals.mean()
    std = history_vals.std(ddof=1)
    
    if std == 0 or pd.isna(std):
        return 0.0
        
    return (current_val - mean) / std


def calculate_sector_momentum_scores(
    sector_summary: pd.DataFrame, 
    sector_history_stats: pd.DataFrame
) -> pd.DataFrame:
    """
    各セクターの4要素複合モメンタムスコアを計算する。
    
    要素：
    1. Zスコア (30%)
    2. RVOL (30%) ※sector_summaryの avg_volume_ratio は既に当日の予測RVOL計算済みとする
    3. 25MA乖離率 (20%) ※ここでは avg_ppo (5MAと25MAの乖離) または別途25MA乖離を用いる
    4. 騰落レシオ (20%)
    
    引数:
        sector_summary: 今日のセクター別サマリーデータ
        sector_history_stats: 過去20日間の各セクターの騰落率データ
            (columns: ['date', 'sector', 'avg_percent_change'])
            
    戻り値:
        モメンタムスコア（0-100）を含むDataFrame
    """
    if sector_summary.empty:
        return sector_summary
        
    df = sector_summary.copy()
    
    # --- 1. Zスコアの計算 ---
    df['z_score'] = 0.0
    if not sector_history_stats.empty:
        for idx, row in df.iterrows():
            sec = row['sector']
            cur_pct = row['avg_percent_change']
            
            # 過去の該当セクターの履歴を取得（当日を除く過去のデータ）
            hist = sector_history_stats[sector_history_stats['sector'] == sec]['avg_percent_change']
            
            df.at[idx, 'z_score'] = calculate_z_score(cur_pct, hist)
    
    # 騰落レシオ (up_down_ratio) は db_manager側/dashboard側で計算されて渡される想定。
    # なければ0.5(中立)で仮置き
    if 'up_down_ratio' not in df.columns:
        df['up_down_ratio'] = 0.5
        
    # --- スコアの正規化 (パーセンタイルランク化して0-100にする) ---
    
    # 1. Zスコア (高い方が良い)
    df['n_z_score'] = df['z_score'].rank(pct=True) * 100
    
    # 2. RVOL (出来高倍率 - avg_volume_ratioが高い方が良い)
    # （※本来なら価格がマイナスの時の出来高急増はネガティブだが、ここでは単純に市場の注目度として「絶対値またはプラス方向の資金流入」を重視する）
    # 今回の要件は「資金流入を見る」なので、
    # 騰落率がプラスの時に出来高が伴っているものを高く評価し、マイナス時の出来高急増はパニック売りとするため、方向性を持たせる
    # ここでは、RVOLの絶対値的な勢いを評価しつつ、総合的に加味する。
    # 上昇方向と下落方向で出来高の意味が変わるが、単純化して「買い勢力・売り勢力の強さ」として扱う
    
    # RVOLに騰落率の符号をかける（プラスなら流入で出来高が多いほどポジティブ、マイナスなら流出で出来高が多いほどネガティブ）
    # ただし「強い資金流入(Inflow)」と「強い資金流出(Outflow)」を分けて考えるため、
    # ここでは「総合スコアが高い＝強い上昇・流入」「総合スコアが低い＝強い下落・流出」となるようにする。
    
    # 符号付きRVOL
    sign = np.sign(df['avg_percent_change'])
    sign = sign.replace(0, 1) # 0のときは1として扱う
    
    # RVOLが大きいほど極端な動きになるよう符号をかけてランキング
    df['signed_rvol'] = df['avg_volume_ratio'] * sign
    df['n_rvol'] = df['signed_rvol'].rank(pct=True) * 100
    
    # 3. 25MA乖離率 (ここでは avg_ppo/avg_sma25_div を使用)
    df['n_ma_div'] = df['avg_ppo'].rank(pct=True) * 100
    
    # 4. 騰落レシオ
    df['n_up_down'] = df['up_down_ratio'].rank(pct=True) * 100
    
    # --- 総合スコアの合成 ---
    # ウェイト: Zスコア=0.3, RVOL=0.3, 25MA乖離=0.2, 騰落レシオ=0.2
    df['momentum_score'] = (
        df['n_z_score'] * 0.30 +
        df['n_rvol'] * 0.30 +
        df['n_ma_div'] * 0.20 +
        df['n_up_down'] * 0.20
    ).round(0).astype(int)
    
    # 0-100の範囲内にクリップする
    df['momentum_score'] = df['momentum_score'].clip(0, 100)
    
    return df
