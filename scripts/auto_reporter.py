# -*- coding: utf-8 -*-
"""
朝刊レポート自動配信スクリプト (auto_reporter.py)
 - 株価データをyfinanceから取得してDBに保存し、
 - Gemini AIで深層分析し、LINE Messaging API経由でプッシュ通知します。
 - タスクスケジューラやcronによる毎朝の定期実行を想定しています。
 - Streamlit不要のヘッドレス実行スクリプトです。
"""

import sys
import os
import requests
import datetime
import traceback

# プロジェクトルートのパスを追加してmodulesを読み込めるようにする
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# .envファイルを手動で読み込む（dotenvライブラリに依存しない）
_env_path = os.path.join(_ROOT, ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# Streamlitに依存しないモジュールのみをインポートする
from modules.db_manager import (
    init_db,
    get_sector_summary,
    get_oversold_stocks,
    get_volume_surge_stocks,
    db_exists,
    upsert_market_data
)
from modules.market_data_fetcher import fetch_all_stocks
from modules.technical_analysis import get_latest_indicators
from modules.jpx_stock_list import get_all_stocks, get_ticker_to_sector, get_ticker_to_name
from modules.market_overview import fetch_market_overview
from modules.news_fetcher import fetch_news_summary
from modules.ai_analyzer import analyze_with_gemini, analyze_for_line

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")


def send_line_message(message: str) -> bool:
    """LINE Messaging API経由でプッシュメッセージを送信する"""
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        print("エラー: .env に LINE_CHANNEL_ACCESS_TOKEN または LINE_USER_ID が設定されていません。")
        return False

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    # LINEのテキストメッセージは最大5000文字の制限があるため超えた分はカットする
    max_len = 4900
    if len(message) > max_len:
        message = message[:max_len] + "\n\n...（文字数制限のため省略）"

    data = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": message}]
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        print("LINE送信: 成功")
        return True
    except requests.exceptions.RequestException as e:
        print(f"LINE送信: 失敗 - {e}")
        return False


def update_db():
    """
    株価データをyfinanceから取得してDBに保存する（ヘッドレス版）
    dashboard.pyの_run_data_update()と同等の処理を、Streamlit不要で実行する
    """
    print("DB更新: 銘柄リストを取得中...")
    stocks = get_all_stocks()
    tickers = [t for t, _, _ in stocks]
    sector_map = get_ticker_to_sector()
    name_map = get_ticker_to_name()

    print(f"DB更新: {len(tickers)} 銘柄のデータをyfinanceから取得中...")
    raw_data = fetch_all_stocks(tickers, period="6mo")

    if not raw_data:
        print("DB更新: データを取得できませんでした。")
        return False

    print(f"DB更新: テクニカル指標を計算してDB保存中... ({len(raw_data)} 銘柄)")
    records = []
    for ticker, df in raw_data.items():
        try:
            indicators = get_latest_indicators(df)
            if indicators and indicators.get("close"):
                indicators["ticker"] = ticker
                indicators["name"] = name_map.get(ticker, "")
                indicators["sector"] = sector_map.get(ticker, "不明")
                records.append(indicators)
        except Exception:
            pass

    if records:
        upsert_market_data(records)
        print(f"DB更新: 完了 ({len(records)} 銘柄を保存)")
        return True
    else:
        print("DB更新: 有効なデータがありませんでした。")
        return False


def main():
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    print(f"=== 朝刊レポート自動配信を開始します ({now.strftime('%Y-%m-%d %H:%M:%S')} JST) ===")

    # DBの初期化
    init_db()

    # 1. DB更新（株価データをyfinanceから取得して保存）
    # ※ 市場が開いている場合は当日データが不完全なため、
    #   平日09:00-15:30以外（夜間・早朝・休日）の実行を推奨
    print("[1/5] DB更新開始...")
    try:
        update_db()
    except Exception as e:
        print(f"DB更新でエラーが発生（スキップして続行）: {e}")

    # DBに有効なデータがあるか確認
    if not db_exists():
        msg = "AI朝刊: DBデータがありません。データの取得に失敗した可能性があります。"
        print(msg)
        send_line_message(msg)
        return

    # 2. マクロ指標の取得（日経先物、米国株など）
    print("[2/5] マクロ指標を取得中...")
    try:
        market_overview = fetch_market_overview()
        print("      完了")
    except Exception as e:
        print(f"      失敗（スキップ）: {e}")
        market_overview = None

    # 3. ニュースの取得
    print("[3/5] 最新ニュースを取得中...")
    try:
        news_text = fetch_news_summary(max_articles=15)
        print("      完了")
    except Exception as e:
        print(f"      失敗（スキップ）: {e}")
        news_text = "ニュースの取得に失敗しました。"

    # 4. DBから最新の分析データを抽出
    sector_summary = get_sector_summary(None)
    oversold_stocks = get_oversold_stocks(None)
    volume_surge_stocks = get_volume_surge_stocks(None)

    # 5. Gemini AI 分析の実行 (LINE専用の要約版)
    print("[4/5] Gemini AIでLINE用レポートを生成中...")
    try:
        report = analyze_for_line(sector_summary, oversold_stocks, volume_surge_stocks, news_text, market_overview)
        print("      完了")
    except Exception as e:
        print(f"      失敗: {e}")
        traceback.print_exc()
        report = f"AI分析中にエラーが発生しました。\n{str(e)}"

    # 6. レポートの整形と送信
    date_str = now.strftime("%m/%d %H:%M")
    header = f"AI朝刊マーケットレポート ({date_str} JST)\n" + "=" * 30 + "\n"
    # 短縮版ではMarkdown記法をプロンプトで禁止しているが、念のため残す
    formatted_report = report.replace("## ", "■ ").replace("### ", "・ ").replace("**", "")
    final_message = f"{header}\n{formatted_report}"

    print("[5/5] LINEへ送信中...")
    send_line_message(final_message)

    print("=== 全処理が完了しました ===")


if __name__ == "__main__":
    main()
