# -*- coding: utf-8 -*-
"""
SQLiteデータベース管理モジュール
- market_dataテーブルの作成・管理
- Index最適化
- Upsert処理
"""

import sqlite3
import os
import pandas as pd
from datetime import datetime

# データベースファイルパス
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "sector_rotation.db")


def get_connection() -> sqlite3.Connection:
    """データベース接続を取得する（ディレクトリが無ければ自動作成）"""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")  # 書き込み性能向上
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    """データベースとテーブルを初期化する"""
    conn = get_connection()
    cursor = conn.cursor()

    # market_dataテーブル作成
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_data (
            date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            name TEXT DEFAULT '',
            sector TEXT DEFAULT '',
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            rsi REAL,
            sma5 REAL,
            sma25 REAL,
            sma75 REAL,
            ppo REAL,
            volume_ratio REAL,
            PRIMARY KEY (date, ticker)
        )
    """)

    # パフォーマンス最適化: Indexの作成
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_data_date
        ON market_data (date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_data_sector
        ON market_data (sector)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_data_ticker
        ON market_data (ticker)
    """)

    conn.commit()
    conn.close()


def upsert_market_data(records: list[dict]):
    """
    市場データをUpsertする（INSERT OR REPLACE）
    records: [{"date": "2024-01-01", "ticker": "7203.T", ...}, ...]
    """
    if not records:
        return

    conn = get_connection()
    cursor = conn.cursor()

    cursor.executemany("""
        INSERT OR REPLACE INTO market_data
        (date, ticker, name, sector, open, high, low, close, volume,
         rsi, sma5, sma25, sma75, ppo, volume_ratio)
        VALUES
        (:date, :ticker, :name, :sector, :open, :high, :low, :close, :volume,
         :rsi, :sma5, :sma25, :sma75, :ppo, :volume_ratio)
    """, records)

    conn.commit()
    conn.close()


def get_latest_date() -> str | None:
    """データベース内の最新日付を返す"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(date) FROM market_data")
    result = cursor.fetchone()
    conn.close()
    return result[0] if result and result[0] else None


def get_latest_data() -> pd.DataFrame:
    """最新日付の全銘柄データをDataFrameで返す"""
    latest_date = get_latest_date()
    if not latest_date:
        return pd.DataFrame()

    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM market_data WHERE date = ?",
        conn, params=(latest_date,)
    )
    conn.close()
    return df


def get_data_by_date_range(start_date: str, end_date: str) -> pd.DataFrame:
    """日付範囲を指定してデータを取得する"""
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM market_data WHERE date BETWEEN ? AND ? ORDER BY date, ticker",
        conn, params=(start_date, end_date)
    )
    conn.close()
    return df


def get_sector_summary(date: str = None) -> pd.DataFrame:
    """セクター別サマリーを取得する"""
    if date is None:
        date = get_latest_date()
    if not date:
        return pd.DataFrame()

    conn = get_connection()
    cursor = conn.cursor()
    # 前営業日を取得して前日比を計算できるようにする
    cursor.execute("SELECT MAX(date) FROM market_data WHERE date < ?", (date,))
    prev_date_row = cursor.fetchone()
    prev_date = prev_date_row[0] if prev_date_row else None

    if prev_date:
        query = """
            SELECT 
                t1.sector,
                COUNT(t1.ticker) as stock_count,
                AVG(t1.rsi) as avg_rsi,
                AVG(t1.volume_ratio) as avg_volume_ratio,
                SUM(t1.close * t1.volume) as trading_value,
                AVG((t1.close - t2.close) / t2.close * 100) as avg_percent_change
            FROM market_data t1
            LEFT JOIN market_data t2 ON t1.ticker = t2.ticker AND t2.date = ?
            WHERE t1.date = ?
            GROUP BY t1.sector
            ORDER BY trading_value DESC
        """
        params = (prev_date, date)
    else:
        query = """
            SELECT
                sector,
                COUNT(*) as stock_count,
                AVG(rsi) as avg_rsi,
                AVG(volume_ratio) as avg_volume_ratio,
                SUM(close * volume) as trading_value,
                0.0 as avg_percent_change
            FROM market_data
            WHERE date = ?
            GROUP BY sector
            ORDER BY trading_value DESC
        """
        params = (date,)

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_oversold_stocks(date: str = None, rsi_threshold: float = 30.0) -> pd.DataFrame:
    """RSIが閾値以下の売られすぎ銘柄を取得する"""
    if date is None:
        date = get_latest_date()
    if not date:
        return pd.DataFrame()

    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM market_data WHERE date = ? AND rsi <= ? ORDER BY rsi ASC",
        conn, params=(date, rsi_threshold)
    )
    conn.close()
    return df


def get_volume_surge_stocks(date: str = None, ratio_threshold: float = 2.0) -> pd.DataFrame:
    """出来高急増銘柄を取得する"""
    if date is None:
        date = get_latest_date()
    if not date:
        return pd.DataFrame()

    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM market_data WHERE date = ? AND volume_ratio >= ? ORDER BY volume_ratio DESC",
        conn, params=(date, ratio_threshold)
    )
    conn.close()
    return df


def get_ticker_history(ticker: str, days: int = 60) -> pd.DataFrame:
    """特定銘柄の履歴データを取得する"""
    conn = get_connection()
    df = pd.read_sql_query(
        """SELECT * FROM market_data
           WHERE ticker = ?
           ORDER BY date DESC
           LIMIT ?""",
        conn, params=(ticker, days)
    )
    conn.close()
    return df.sort_values("date") if not df.empty else df


def get_all_dates() -> list[str]:
    """データベース内の全日付リストを返す（降順）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT date FROM market_data ORDER BY date DESC")
    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return dates


def get_db_last_modified() -> float:
    """データベースファイル（またはそのディレクトリ）の最終更新日時をタイムスタンプで返す"""
    # DBファイルが存在しない場合はディレクトリの更新日時、それもなければ0を返す
    if os.path.exists(DB_PATH):
        return os.path.getmtime(DB_PATH)
    elif os.path.exists(DB_DIR):
        return os.path.getmtime(DB_DIR)
    return 0.0


def db_exists() -> bool:
    """データベースファイルが存在し、データがあるかチェックする"""
    if not os.path.exists(DB_PATH):
        return False
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM market_data")
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False
