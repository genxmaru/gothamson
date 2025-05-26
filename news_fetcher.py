import feedparser
import json
import re
from datetime import datetime, timezone
import os

# 設定ファイルのパス
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config', 'keywords.json')
# 処理済み記事ログファイルのパス
PROCESSED_ARTICLES_LOG = os.path.join(os.path.dirname(__file__), 'data', 'processed_articles.json')
# 毎時キーワードカウントログファイルのパス
HOURLY_KEYWORD_COUNTS_LOG = os.path.join(os.path.dirname(__file__), 'data', 'hourly_keyword_counts.jsonl')

def load_config():
    """設定ファイルからキーワードとRSSフィードをロードする"""
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: Config file not found at {CONFIG_FILE}")
        return {"keywords": [], "rss_feeds": []}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_processed_articles():
    """処理済み記事のURLをロードする"""
    if not os.path.exists(PROCESSED_ARTICLES_LOG):
        return {}
    with open(PROCESSED_ARTICLES_LOG, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {} # ファイルが空または不正な場合は空の辞書を返す

def save_processed_articles(processed_articles):
    """処理済み記事のURLを保存する"""
    with open(PROCESSED_ARTICLES_LOG, 'w', encoding='utf-8') as f:
        json.dump(processed_articles, f, ensure_ascii=False, indent=4)

def _log_hourly_keyword_counts(timestamp, keyword_counts):
    """毎時のキーワードカウントをJSONL形式で追記する"""
    entry = {
        "timestamp": timestamp.isoformat(),
        "counts": keyword_counts
    }
    with open(HOURLY_KEYWORD_COUNTS_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')

def _log_processed_article(timestamp, article_data):
    """処理済み記事のログを追記する"""
    # ここは、processed_articles.json に直接書き込むのではなく、メモリ上の辞書を更新して後でまとめて保存する
    # すでに load_processed_articles と save_processed_articles があるので、この関数は不要
    pass

def fetch_and_log_keywords():
    """RSSフィードから記事を取得し、キーワードを検知・ログに記録する"""
    config = load_config()
    keywords = config.get("keywords", [])
    rss_feeds = config.get("rss_feeds", [])

    # 大文字・小文字を区別しない正規表現パターンをコンパイル
    keyword_patterns = {
        keyword: re.compile(r'\b' + re.escape(keyword) + r'\b', re.IGNORECASE)
        for keyword in keywords
    }

    processed_articles = load_processed_articles()

    current_time = datetime.now(timezone.utc)
    hourly_counts_by_source = {} # サイト別にキーワードカウントを保持

    print(f"Fetching news at {current_time.isoformat()}...")

    for feed_info in rss_feeds:
        feed_name = feed_info.get("name", "Unknown Source")
        feed_url = feed_info.get("url")

        if not feed_url:
            print(f"Skipping feed with no URL: {feed_info}")
            continue

        print(f"Processing feed: {feed_name} ({feed_url})")
        feed = feedparser.parse(feed_url)

        if feed.bozo:
            print(f"Warning: Could not parse feed {feed_url} - {feed.bozo_exception}")
            continue

        for entry in feed.entries:
            # 記事のユニークなIDとしてURLを使用 (またはGUIDがあればGUID)
            article_id = entry.link

            # すでに処理済みの記事であればスキップ
            if article_id in processed_articles:
                continue

            title = getattr(entry, 'title', '')
            summary = getattr(entry, 'summary', getattr(entry, 'description', ''))
            content = getattr(entry, 'content', [])

            full_text = title + " " + summary
            for c in content:
                if hasattr(c, 'value'):
                    full_text += " " + c.value

            # 記事ごとにキーワードをカウント
            article_keyword_counts = {}
            for keyword, pattern in keyword_patterns.items():
                count = len(pattern.findall(full_text))
                if count > 0:
                    article_keyword_counts[keyword] = count

            if article_keyword_counts:
                # hourly_counts_by_source にサイト別、キーワード別のカウントを追加
                if feed_name not in hourly_counts_by_source:
                    hourly_counts_by_source[feed_name] = {}
                for keyword, count in article_keyword_counts.items():
                    hourly_counts_by_source[feed_name][keyword] = \
                        hourly_counts_by_source[feed_name].get(keyword, 0) + count

            # 処理済み記事として記録
            processed_articles[article_id] = {
                "last_processed": current_time.isoformat(),
                "keywords": list(article_keyword_counts.keys()), # 検知されたキーワードのみ
                "source": feed_name # ★ここを追加★ ニュースソース名
            }

    # サイトごとの集計結果を hourly_keyword_counts.jsonl に記録
    if hourly_counts_by_source:
        # hourly_keyword_counts.jsonl に保存する形式を、サイト名ごとの集計に調整
        log_entry_counts = {
            "timestamp": current_time.isoformat(),
            "sources": hourly_counts_by_source # サイト別に集計結果を格納
        }
        with open(HOURLY_KEYWORD_COUNTS_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry_counts, ensure_ascii=False) + '\n')
        print(f"Logged hourly keyword counts for {len(hourly_counts_by_source)} sources.")
    else:
        print("No new keywords detected in this run.")

    # 処理済み記事リストを保存
    save_processed_articles(processed_articles)
    print("Updated processed_articles.json.")

if __name__ == "__main__":
    fetch_and_log_keywords()
