# -*- coding: utf-8 -*-
"""
RSSニュース収集モジュール（AI分析強化版）
- feedparserを使用
- Yahoo!ニュース、ロイター等から「見出し」＋「要約」を取得
- AIが文脈を理解できるように情報をリッチにする
"""

import feedparser
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
import time

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

def parse_pub_date(entry) -> datetime | None:
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

def fetch_news(hours: int = 24) -> list[dict]:
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

                # 日時フィルタ（日時が取れない場合は一応含めるか、厳密にするか。ここは厳密に除外）
                if pub_date and pub_date < cutoff_time:
                    continue

                title = entry.get("title", "タイトルなし")
                link = entry.get("link", "")
                pub_str = pub_date.strftime("%Y-%m-%d %H:%M") if pub_date else "日時不明"
                
                # 【重要】要約（中身）を取得するロジック
                # summary, description の順で探す
                raw_summary = entry.get("summary", entry.get("description", ""))
                
                # HTMLタグを消してきれいにする
                summary = clean_html(raw_summary)

                all_articles.append({
                    "title": title,
                    "summary": summary,  # ここがAIにとっての「栄養」になります
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

def fetch_news_summary(max_articles: int =
