# news_fetcher.py v0.2 — RSS版
import feedparser
from datetime import datetime

def fetch_coindesk_articles():
    rss_url = 'https://www.coindesk.com/arc/outboundfeeds/rss/'  # CoinDesk公式RSSフィード :contentReference[oaicite:0]{index=0}
    feed = feedparser.parse(rss_url)
    articles = []

    for entry in feed.entries:
        # published_parsed が利用可能なら日付をパース
        if hasattr(entry, 'published_parsed'):
            pub_date = datetime(*entry.published_parsed[:6]).strftime('%Y-%m-%d')
        else:
            pub_date = datetime.utcnow().strftime('%Y-%m-%d')
        articles.append({
            'date': pub_date,
            'source': 'CoinDesk',
            'title': entry.title,
            'url': entry.link
        })
    return articles

if __name__ == '__main__':
    for a in fetch_coindesk_articles():
        print(f"{a['date']} | {a['source']} | {a['title']} | {a['url']}")
