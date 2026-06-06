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
            percent_change REAL,
            PRIMARY KEY (date, ticker)
        )
    """)

    # 既存DBへのカラム追加（エラー無視）
    try:
        cursor.execute("ALTER TABLE market_data ADD COLUMN percent_change REAL")
    except sqlite3.OperationalError:
        pass

    # stock_fundamentalsテーブル作成
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_fundamentals (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            sector TEXT,
            per REAL,
            pbr REAL,
            market_cap REAL,
            updated_at TEXT
        )
    """)

    # shikiho_fundamentalsテーブル作成（四季報・最強銘柄スナイパー用）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shikiho_fundamentals (
            code TEXT PRIMARY KEY,
            name TEXT,
            sales_growth REAL,
            op_profit_growth REAL,
            op_profit_margin REAL,
            reason TEXT,
            csv_updated_at TEXT
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
         rsi, sma5, sma25, sma75, ppo, volume_ratio, percent_change)
        VALUES
        (:date, :ticker, :name, :sector, :open, :high, :low, :close, :volume,
         :rsi, :sma5, :sma25, :sma75, :ppo, :volume_ratio, :percent_change)
    """, records)

    conn.commit()
    conn.close()


def upsert_fundamentals(records: list[dict]):
    """
    ファンダメンタルズデータをUpsertする
    records: [{"ticker": "7203.T", "name": "トヨタ", "sector": "...", "per": 10.0, "pbr": 1.0, "market_cap": 1000000000, "updated_at": "2023-10-01 10:00:00"}, ...]
    """
    if not records:
        return

    conn = get_connection()
    cursor = conn.cursor()

    cursor.executemany("""
        INSERT OR REPLACE INTO stock_fundamentals
        (ticker, name, sector, per, pbr, market_cap, updated_at)
        VALUES
        (:ticker, :name, :sector, :per, :pbr, :market_cap, :updated_at)
    """, records)

    conn.commit()
    conn.close()


def get_fundamentals(tickers: list[str]) -> pd.DataFrame:
    """指定されたティッカーリストのファンダメンタルズを取得する"""
    if not tickers:
        return pd.DataFrame()

    conn = get_connection()
    placeholders = ",".join(["?"] * len(tickers))
    df = pd.read_sql_query(
        f"SELECT * FROM stock_fundamentals WHERE ticker IN ({placeholders})",
        conn, params=tickers
    )
    conn.close()
    return df


def get_all_fundamentals() -> pd.DataFrame:
    """DBに保存されている全てのファンダメンタルズを取得する"""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM stock_fundamentals", conn)
    conn.close()
    return df

# =========================================================================
# 四季報・最強銘柄スナイパー用メソッド
# =========================================================================

def import_shikiho_csv(csv_path: str) -> bool:
    """
    四季報トップ50のCSVを読み込み、正規表現で動的にカラムを特定して
    shikiho_fundamentalsテーブルへUpsertする。
    """
    if not os.path.exists(csv_path):
        print(f"⚠️ 四季報CSVが見つかりません: {csv_path}")
        return False
        
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"⚠️ 四季報CSVの読み込みに失敗: {e}")
        return False
        
    # 動的カラム解決
    cols = df.columns.tolist()
    
    code_col = next((c for c in cols if "コード" in c), None)
    name_col = next((c for c in cols if "銘柄名" in c or "名称" in c), None)
    sales_col = next((c for c in cols if "売上成長率" in c), None)
    op_grown_col = next((c for c in cols if "営業益成長率" in c or "営業利益成長率" in c), None)
    op_margin_col = next((c for c in cols if "営業利益率" in c), None)
    reason_col = next((c for c in cols if "選定理由" in c or "強み" in c), None)
    
    if not code_col or not reason_col:
        print("⚠️ 必須カラム（コード、選定理由）が見つかりません。")
        return False
        
    # クリーニング用関数
    def clean_pct(val):
        if pd.isna(val) or val == "" or str(val).strip() == "":
            return None
        s = str(val).replace("%", "").replace("+", "").replace(",", "").strip()
        try:
            return float(s)
        except ValueError:
            return None
            
    # レコード作成
    # CSVファイルの更新日時を取得
    import time
    file_mtime = os.path.getmtime(csv_path)
    updated_at = datetime.fromtimestamp(file_mtime).strftime("%Y-%m-%d %H:%M:%S")
    
    records = []
    for _, row in df.iterrows():
        code_val = row.get(code_col)
        # 空行や"順位"がNaNの行をスキップ
        if pd.isna(code_val) or str(code_val).strip() == "":
            continue
            
        str_code = str(code_val).strip()
        # "1234.0" のようになっている場合は ".0" を削る
        if str_code.endswith(".0"):
            str_code = str_code[:-2]
        
        code = str_code + ".T" # yfinance用の.T付与
        name = str(row.get(name_col, ""))
        reason = str(row.get(reason_col, ""))
        
        sales_growth = clean_pct(row.get(sales_col))
        op_profit_growth = clean_pct(row.get(op_grown_col))
        op_profit_margin = clean_pct(row.get(op_margin_col))
        
        records.append({
            "code": code,
            "name": name,
            "sales_growth": sales_growth,
            "op_profit_growth": op_profit_growth,
            "op_profit_margin": op_profit_margin,
            "reason": reason,
            "csv_updated_at": updated_at
        })
        
    if not records:
        print("⚠️ インポートできる有効なデータがありませんでした。")
        return False
        
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.executemany("""
        INSERT OR REPLACE INTO shikiho_fundamentals
        (code, name, sales_growth, op_profit_growth, op_profit_margin, reason, csv_updated_at)
        VALUES
        (:code, :name, :sales_growth, :op_profit_growth, :op_profit_margin, :reason, :csv_updated_at)
    """, records)
    
    conn.commit()
    conn.close()
    print(f"✅ 四季報データ {len(records)}件 のインポートが完了しました。")
    return True

def get_shikiho_data() -> pd.DataFrame:
    """DBから四季報ファンダメンタルズデータを取得する"""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM shikiho_fundamentals", conn)
    conn.close()
    return df


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
    df = pd.read_sql_query("""
        SELECT
            sector,
            COUNT(*) as stock_count,
            AVG(rsi) as avg_rsi,
            AVG(volume_ratio) as avg_volume_ratio,
            SUM(close * volume) as trading_value,
            AVG(percent_change) as avg_percent_change,
            AVG(ppo) as avg_ppo
        FROM market_data
        WHERE date = ?
        GROUP BY sector
        ORDER BY trading_value DESC
    """, conn, params=(date,))
    conn.close()
    return df


def get_sector_history_stats(date: str = None, days: int = 20) -> pd.DataFrame:
    """
    指定した日付から過去N日間の各セクターの平均騰落率（前日比）等を取得する。
    Zスコア計算時の標準偏差・平均の算出に使用する。
    """
    if date is None:
        date = get_latest_date()
    if not date:
        return pd.DataFrame()

    conn = get_connection()
    df = pd.read_sql_query(f"""
        SELECT date, sector, AVG(percent_change) as avg_percent_change
        FROM market_data
        WHERE date <= ? AND date >= date(?, '-{days * 2} days') -- 休場日を考慮し多めに取得
        GROUP BY date, sector
        ORDER BY date DESC
    """, conn, params=(date, date))
    conn.close()
    
    # 最新の20営業日を抽出する
    if not df.empty:
        dates = df['date'].unique()
        target_dates = dates[:days]
        df = df[df['date'].isin(target_dates)]
        
    return df

def get_sector_trajectory(date: str = None, days: int = 4) -> pd.DataFrame:
    """
    指定した日付から過去N日間（デフォルト4日＝本日＋過去3日分）の
    各セクターの平均PPOとRSIを取得する。
    散布図（レーダーチャート）の軌跡（しっぽ）描画に使用する。
    """
    if date is None:
        date = get_latest_date()
    if not date:
        return pd.DataFrame()

    conn = get_connection()
    df = pd.read_sql_query(f"""
        SELECT date, sector, AVG(ppo) as avg_ppo, AVG(rsi) as avg_rsi
        FROM market_data
        WHERE date <= ? AND date >= date(?, '-{days * 2} days') -- 休場日を考慮
        GROUP BY date, sector
        ORDER BY date DESC
    """, conn, params=(date, date))
    conn.close()
    
    if not df.empty:
        dates = df['date'].unique()
        target_dates = dates[:days]
        df = df[df['date'].isin(target_dates)].sort_values(['sector', 'date'])
        
    return df


def get_advanced_sector_summary(date: str = None) -> pd.DataFrame:
    """
    セクター別サマリーを取得する。
    従来の指標に加え、騰落レシオ（前日比プラスの銘柄割合）などの高度な指標も算出する。
    """
    if date is None:
        date = get_latest_date()
    if not date:
        return pd.DataFrame()

    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT
            sector,
            COUNT(*) as stock_count,
            SUM(CASE WHEN percent_change > 0.01 THEN 1 ELSE 0 END) as up_count,
            AVG(rsi) as avg_rsi,
            AVG(volume_ratio) as avg_volume_ratio,
            SUM(close * volume) as trading_value,
            AVG(percent_change) as avg_percent_change,
            AVG(ppo) as avg_ppo
        FROM market_data
        WHERE date = ?
        GROUP BY sector
    """, conn, params=(date,))
    conn.close()
    
    if not df.empty:
        # 騰落レシオ (0.0 - 1.0)
        df['up_down_ratio'] = df['up_count'] / df['stock_count']
        
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
