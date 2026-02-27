# -*- coding: utf-8 -*-
"""
銘柄リスト更新スクリプト
JPXから上場銘柄一覧を取得し、プライム・スタンダード市場の
売買代金上位600銘柄を抽出して utils/constants.py に書き込む

使い方:
    python scripts/update_stock_list.py
"""

import os
import sys
import time
import pandas as pd
import yfinance as yf
from io import BytesIO
import requests

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# JPX上場銘柄一覧のExcelファイルURL
JPX_LISTED_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"

# 対象市場
TARGET_MARKETS = ["プライム（内国株式）", "スタンダード（内国株式）"]

# 出力先
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "utils", "constants.py")

# 取得設定
BATCH_SIZE = 50
TOP_N = 600


def download_jpx_list() -> pd.DataFrame:
    """JPXから上場銘柄一覧をダウンロードする"""
    print("📥 JPX上場銘柄一覧をダウンロード中...")

    try:
        response = requests.get(JPX_LISTED_URL, timeout=30)
        response.raise_for_status()
        df = pd.read_excel(BytesIO(response.content))
        print(f"  → {len(df)} 銘柄を取得")
        return df
    except Exception as e:
        print(f"❌ JPXデータの取得に失敗: {e}")
        print("  フォールバック: ローカルの銘柄リストを使用します")
        return pd.DataFrame()


def filter_target_markets(df: pd.DataFrame) -> pd.DataFrame:
    """プライム・スタンダード市場の銘柄をフィルタリングする"""
    if df.empty:
        return df

    # カラム名の確認（JPXのExcelフォーマットに対応）
    market_col = None
    for col in df.columns:
        if "市場" in str(col) or "上場" in str(col):
            market_col = col
            break

    if market_col is None:
        print("⚠️ 市場区分カラムが見つかりません。全銘柄を対象とします。")
        return df

    filtered = df[df[market_col].isin(TARGET_MARKETS)]
    print(f"  → プライム・スタンダード: {len(filtered)} 銘柄")
    return filtered


def get_trading_values(tickers: list[str]) -> dict[str, float]:
    """yfinanceで直近の売買代金を取得する"""
    print(f"📊 売買代金を取得中... ({len(tickers)} 銘柄)")
    trading_values = {}
    total = len(tickers)

    for i in range(0, total, BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  バッチ {batch_num}/{total_batches}...")

        try:
            ticker_str = " ".join(batch)
            data = yf.download(
                ticker_str,
                period="5d",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )

            if data.empty:
                continue

            for ticker in batch:
                try:
                    if len(batch) == 1:
                        ticker_data = data
                    else:
                        if isinstance(data.columns, pd.MultiIndex):
                            ticker_data = data.xs(ticker, level="Ticker", axis=1)
                        else:
                            ticker_data = data

                    if not ticker_data.empty:
                        # 売買代金 = 終値 × 出来高 の直近平均
                        close_col = "Close" if "Close" in ticker_data.columns else None
                        vol_col = "Volume" if "Volume" in ticker_data.columns else None

                        if close_col and vol_col:
                            tv = (ticker_data[close_col] * ticker_data[vol_col]).mean()
                            if pd.notna(tv) and tv > 0:
                                trading_values[ticker] = float(tv)
                except Exception:
                    pass

        except Exception as e:
            print(f"  ⚠️ バッチエラー: {e}")

        # レート制限回避
        if i + BATCH_SIZE < total:
            time.sleep(1)

    print(f"  → {len(trading_values)} 銘柄の売買代金を取得")
    return trading_values


def generate_constants_py(stocks: list[tuple[str, str, str]]):
    """utils/constants.py にPythonリストとして書き込む"""
    print(f"\n📝 constants.py を更新中... ({len(stocks)} 銘柄)")

    # セクターごとにグルーピング
    sector_groups = {}
    for ticker, name, sector in stocks:
        if sector not in sector_groups:
            sector_groups[sector] = []
        sector_groups[sector].append((ticker, name, sector))

    lines = [
        '# -*- coding: utf-8 -*-',
        '"""',
        '東証33業種セクター定義 & 売買代金上位600銘柄リスト（静的）',
        'scripts/update_stock_list.py で定期更新可能',
        f'最終更新: {time.strftime("%Y-%m-%d %H:%M:%S")}',
        '"""',
        '',
        '# 東証33業種セクター一覧',
        'SECTORS = [',
        '    "水産・農林業", "鉱業", "建設業", "食料品", "繊維製品",',
        '    "パルプ・紙", "化学", "医薬品", "石油・石炭製品", "ゴム製品",',
        '    "ガラス・土石製品", "鉄鋼", "非鉄金属", "金属製品", "機械",',
        '    "電気機器", "輸送用機器", "精密機器", "その他製品", "電気・ガス業",',
        '    "陸運業", "海運業", "空運業", "倉庫・運輸関連業", "情報・通信業",',
        '    "卸売業", "小売業", "銀行業", "証券、商品先物取引業", "保険業",',
        '    "その他金融業", "不動産業", "サービス業",',
        ']',
        '',
        '# 売買代金上位銘柄リスト',
        '# フォーマット: (ティッカー, 銘柄名, セクター)',
        'STOCK_LIST = [',
    ]

    for sector in sorted(sector_groups.keys()):
        lines.append(f'    # ===== {sector} =====')
        for ticker, name, sec in sector_groups[sector]:
            lines.append(f'    ("{ticker}", "{name}", "{sec}"),')

    lines.append(']')
    lines.append('')
    lines.append('')
    lines.append('def get_stock_list():')
    lines.append('    """重複を除いた銘柄リストを返す"""')
    lines.append('    seen = set()')
    lines.append('    unique_list = []')
    lines.append('    for ticker, name, sector in STOCK_LIST:')
    lines.append('        if ticker not in seen:')
    lines.append('            seen.add(ticker)')
    lines.append('            unique_list.append((ticker, name, sector))')
    lines.append('    return unique_list')
    lines.append('')
    lines.append('')
    lines.append('def get_tickers():')
    lines.append('    """ティッカーシンボルのリストのみを返す"""')
    lines.append('    return [t for t, _, _ in get_stock_list()]')
    lines.append('')
    lines.append('')
    lines.append('def get_sector_map():')
    lines.append('    """ティッカー→セクターのマッピング辞書を返す"""')
    lines.append('    return {t: s for t, _, s in get_stock_list()}')
    lines.append('')
    lines.append('')
    lines.append('def get_name_map():')
    lines.append('    """ティッカー→銘柄名のマッピング辞書を返す"""')
    lines.append('    return {t: n for t, n, _ in get_stock_list()}')
    lines.append('')

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ {OUTPUT_PATH} を更新しました")


def main():
    """メイン実行"""
    print("=" * 60)
    print("  銘柄リスト更新スクリプト")
    print("=" * 60)

    # 1. JPXから銘柄一覧をダウンロード
    jpx_df = download_jpx_list()

    if jpx_df.empty:
        print("❌ JPXデータを取得できません。処理を終了します。")
        return

    # 2. プライム・スタンダード市場をフィルタリング
    filtered = filter_target_markets(jpx_df)

    if filtered.empty:
        print("❌ フィルタリング結果が空です。")
        return

    # 3. ティッカーシンボルを生成
    # 実際のJPX Excelカラム名: 'コード', '銘柄名', '33業種区分'
    code_col = None
    name_col = None
    sector_col = None

    for col in filtered.columns:
        col_str = str(col).strip()
        if col_str == "コード" and code_col is None:
            code_col = col
        elif col_str == "銘柄名" and name_col is None:
            name_col = col
        elif col_str == "33業種区分" and sector_col is None:
            sector_col = col

    if code_col is None:
        print("❌ 銘柄コードカラムが見つかりません")
        return

    # ティッカー生成（4桁コード → XXXX.T 形式）
    tickers_info = []
    for _, row in filtered.iterrows():
        try:
            code = str(int(row[code_col]))
            ticker = f"{code}.T"
            name = str(row[name_col]) if name_col else ""
            sector = str(row[sector_col]) if sector_col else "不明"
            tickers_info.append((ticker, name, sector))
        except (ValueError, TypeError):
            pass

    print(f"\n📋 対象銘柄: {len(tickers_info)} 件")

    # 4. 売買代金を取得
    tickers = [t for t, _, _ in tickers_info]
    trading_values = get_trading_values(tickers)

    # 5. 売買代金でソートし上位600を抽出
    ticker_info_map = {t: (n, s) for t, n, s in tickers_info}
    ranked = sorted(trading_values.items(), key=lambda x: x[1], reverse=True)
    top_stocks = []
    for ticker, tv in ranked[:TOP_N]:
        name, sector = ticker_info_map.get(ticker, ("", "不明"))
        top_stocks.append((ticker, name, sector))

    print(f"\n🏆 売買代金上位 {len(top_stocks)} 銘柄を選出")

    # 6. constants.py に書き込み
    generate_constants_py(top_stocks)

    print("\n✅ 完了！")
    print(f"   {len(top_stocks)} 銘柄が constants.py に書き込まれました。")
    print("   次回アプリ起動時に反映されます。")


if __name__ == "__main__":
    main()
