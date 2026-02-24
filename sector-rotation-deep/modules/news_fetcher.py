# -*- coding: utf-8 -*-
"""
RSSニュース収集モジュール（AI分析強化版）
- Python 3.9以下対応（型ヒントの修正）
- Yahoo!ニュース、ロイター等から「見出し」＋「要約」を取得
"""

import feedparser
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
import time
from typing import List, Dict, Optional # 互換性のために追加

# RSSフィードURL一覧
RSS_FEEDS = [
    {
        "name": "Yahoo!ニュース - 経済",
        "url": "https://news.yahoo.co.jp/rss/topics/business.xml",
    },
    {
        "name": "Yahoo!ニュース - IT",
        "url": "https://news.yahoo.co.jp/rss/topics/it.xml",
    },
    {
        "name": "Yahoo!ファイナンス - 株式",
        "url": "https://finance.yahoo.co.jp/rss/stock.xml",
    },
    {
        "name": "ロイター日本 - ビジネス",
        "url": "https://assets.wor.jp/rss/rdf/reuters/business.rdf",
    },
    {
        "name": "日経 - マーケット",
        "url": "https://assets.wor.jp/rss/rdf/nikkei/markets.rdf",
    },
]

def clean_html(raw_html):
    """HTMLタグを除去してテキストのみ抽出する"""
    if not raw_html:
        return ""
    cleanr = re.compile('<.*?>')
    text = re.sub(cleanr, '', raw_html)
    return text.strip()

def parse_pub_date(entry) -> Optional[datetime]: # 修正箇所：| None を Optional[] に変更
    """RSSエントリから公開日時をパースする"""
    # published_parsed を優先
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass

    # updated_parsed をフォールバック
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        try:
            return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass

    # 文字列パース
    for attr in ("published", "updated", "dc_date"):
        date_str = getattr(entry, attr, None)
        if date_str:
            try:
                return parsedate_to_datetime(date_str)
            except Exception:
                pass
    return None

def fetch_news(hours: int = 24) -> List[Dict]: # 修正箇所：list[dict] を List[Dict] に変更
    """
    全RSSフィードからニュースを取得し、直近指定時間分をフィルタリングする
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    all_articles = []

    for feed_info in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            
            for entry in feed.entries:
                pub_date = parse_pub_date(entry)

                # 日時フィルタ
                if pub_date and pub_date < cutoff_time:
                    continue

                title = entry.get("title", "タイトルなし")
                link = entry.get("link", "")
                pub_str = pub_date.strftime("%Y-%m-%d %H:%M") if pub_date else "日時不明"
                
                # 要約（中身）を取得するロジック
                raw_summary = entry.get("summary", entry.get("description", ""))
                summary = clean_html(raw_summary)

                all_articles.append({
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "published": pub_str,
                    "source": feed_info["name"],
                })

        except Exception as e:
            print(f"Error fetching {feed_info['url']}: {e}")
            continue

    # 公開日時でソート（新しい順）
    all_articles.sort(key=lambda x: x.get("published", ""), reverse=True)

    return all_articles

def fetch_news_summary(max_articles: int = 15) -> str:
    """
    AI分析用のニュースサマリーテキストを生成する
    """
    articles = fetch_news(hours=24)
    
    if not articles:
        return "直近24時間のニュースは取得できませんでした。（RSS接続エラーまたは記事なし）"

    # AIに渡すテキストを組み立てる
    lines = [f"【直近24時間の市況ニュース（重要度順抜粋）】"]
    
    limit = min(len(articles), max_articles)
    
    for i in range(limit):
        article = articles[i]
        lines.append(f"")
        lines.append(f"記事{i+1}. [{article['source']}] {article['title']}")
        lines.append(f"   日付: {article['published']}")
        if article['summary']:
            lines.append(f"   詳細: {article['summary'][:150]}...") 
            
    return "\n".join(lines)

# テスト実行用
if __name__ == "__main__":
    print(fetch_news_summary(5))
