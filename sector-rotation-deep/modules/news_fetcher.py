# -*- coding: utf-8 -*-
"""
RSSニュース収集モジュール
- feedparserを使用
- Yahoo!ニュース経済・IT等のRSSフィードから取得
- 直近24時間のフィルタリング
"""

import feedparser
from datetime import datetime, timedelta, timezone
import time as time_module
from email.utils import parsedate_to_datetime


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


def parse_pub_date(entry) -> datetime | None:
    """
    RSSエントリから公開日時をパースする
    複数フォーマットに対応
    """
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


def fetch_news(hours: int = 24) -> list[dict]:
    """
    全RSSフィードからニュースを取得し、直近指定時間分をフィルタリングする

    Args:
        hours: 何時間前までのニュースを取得するか（デフォルト24時間）

    Returns:
        [{"title": ..., "link": ..., "published": ..., "source": ...}, ...]
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    all_articles = []

    for feed_info in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])

            for entry in feed.entries:
                pub_date = parse_pub_date(entry)

                # 日時が取得できない場合はフィルタリングせずに含める
                if pub_date and pub_date < cutoff_time:
                    continue

                title = entry.get("title", "タイトルなし")
                link = entry.get("link", "")
                pub_str = pub_date.strftime("%Y-%m-%d %H:%M") if pub_date else "日時不明"

                all_articles.append({
                    "title": title,
                    "link": link,
                    "published": pub_str,
                    "source": feed_info["name"],
                })

        except Exception:
            # フィード読み込みエラーはスキップ
            continue

    # 公開日時でソート（新しい順）
    all_articles.sort(key=lambda x: x["published"], reverse=True)

    return all_articles


def fetch_news_summary(max_articles: int = 10) -> str:
    """
    AI分析用のニュースサマリーテキストを生成する

    Args:
        max_articles: 含める最大記事数

    Returns:
        ニュース一覧の文字列
    """
    articles = fetch_news()[:max_articles]

    if not articles:
        return "直近のニュースは取得できませんでした。"

    lines = ["【直近の主要ニュース】"]
    for i, article in enumerate(articles, 1):
        lines.append(f"{i}. [{article['source']}] {article['title']} ({article['published']})")

    return "\n".join(lines)
