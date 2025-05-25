import feedparser
import json
from datetime import datetime, timezone, timedelta
import os
import re

# --- 設定ファイルのパス ---
SOURCES_CONFIG_PATH = "config/sources.json"
KEYWORDS_CONFIG_PATH = "config/keywords.json"

# --- データファイルのパス ---
HOURLY_LOG_PATH = "data/hourly_keyword_counts.jsonl"
PROCESSED_ARTICLES_LOG = "data/processed_articles.json" # 処理済み記事のURLを保存

# --- 処理済み記事ログの保持期間 (時間) ---
# 例: 過去48時間以内に処理した記事は重複と見なす
PROCESSED_LOG_RETENTION_HOURS = 48

def load_config(filepath):
    """指定されたJSONファイルを読み込む"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_jsonl(filepath, data):
    """データをJSON Lines形式でファイルに追記する"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False) + '\n')

def load_processed_articles():
    """処理済み記事のログを読み込む"""
    if os.path.exists(PROCESSED_ARTICLES_LOG):
        with open(PROCESSED_ARTICLES_LOG, 'r', encoding='utf-8') as f:
            try:
                # 辞書として読み込み、日付文字列をdatetimeオブジェクトに変換
                loaded_data = json.load(f)
                processed = {}
                for url, timestamp_str in loaded_data.items():
                    processed[url] = datetime.fromisoformat(timestamp_str)
                return processed
            except json.JSONDecodeError:
                return {}
    return {}

def save_processed_articles(processed_urls):
    """処理済み記事のログを保存する"""
    os.makedirs(os.path.dirname(PROCESSED_ARTICLES_LOG), exist_ok=True)
    # datetimeオブジェクトをISOフォーマットの文字列に変換して保存
    serializable_data = {url: ts.isoformat() for url, ts in processed_urls.items()}
    with open(PROCESSED_ARTICLES_LOG, 'w', encoding='utf-8') as f:
        json.dump(serializable_data, f, ensure_ascii=False, indent=2)

def clean_processed_articles(processed_urls):
    """古い処理済み記事のログを削除する"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=PROCESSED_LOG_RETENTION_HOURS)
    cleaned_urls = {
        url: ts for url, ts in processed_urls.items()
        if ts >= cutoff
    }
    return cleaned_urls

def extract_keywords(text, keywords_list):
    """
    テキストから定義済みキーワードを抽出し、出現回数をカウントする。
    大文字・小文字を区別せず、単語全体としてマッチングする。
    """
    found_keywords = {}
    lower_text = text.lower() # テキストを小文字に変換

    for keyword in keywords_list:
        # 単語の境界(\b)を使って、完全な単語としてマッチング
        # 例: "AI"が"TRAINING"の一部としてマッチしないように
        pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
        matches = len(re.findall(pattern, lower_text))
        if matches > 0:
            found_keywords[keyword] = matches
    return found_keywords

def main():
    sources = load_config(SOURCES_CONFIG_PATH)
    keywords_list = load_config(KEYWORDS_CONFIG_PATH) # キーワードリストをロード

    # 既存の処理済み記事ログを読み込み、古いエントリをクリーンアップ
    processed_articles_data = load_processed_articles()
    processed_articles_data = clean_processed_articles(processed_articles_data)

    current_hourly_counts = {keyword: 0 for keyword in keywords_list}
    newly_processed_urls_this_run = {}

    for source_info in sources:
        print(f"Fetching from {source_info['name']} ({source_info['url']})...")
        feed = feedparser.parse(source_info['url'])

        for entry in feed.entries:
            article_url = entry.link
            # URLが既に処理済みリストにあればスキップ
            if article_url in processed_articles_data:
                continue

            # タイトルとdescription（概要）を結合してキーワードを抽出
            # RSSフィードによってはdescriptionがない場合もある
            article_text = entry.title + " " + getattr(entry, 'summary', '') + " " + getattr(entry, 'description', '')
            
            detected_keywords = extract_keywords(article_text, keywords_list)

            # 検出されたキーワードを現在の時間帯のカウントに加算
            for keyword, count in detected_keywords.items():
                current_hourly_counts[keyword] += count
            
            # 新たに処理した記事としてマーク
            now_utc = datetime.now(timezone.utc)
            processed_articles_data[article_url] = now_utc
            newly_processed_urls_this_run[article_url] = now_utc

    # 1時間ごとの集計結果をログに追記
    timestamp_utc = datetime.now(timezone.utc).isoformat()
    hourly_log_entry = {
        "timestamp": timestamp_utc,
        "keyword_counts": current_hourly_counts,
        "newly_processed_articles_count": len(newly_processed_urls_this_run)
    }
    save_jsonl(HOURLY_LOG_PATH, hourly_log_entry)
    
    # 処理済み記事のログを保存
    save_processed_articles(processed_articles_data)

    print(f"--- Hourly Keyword Counts ({timestamp_utc}) ---")
    for keyword, count in current_hourly_counts.items():
        if count > 0:
            print(f"{keyword}: {count}")
    print(f"Processed {len(newly_processed_urls_this_run)} new articles this run.")


if __name__ == '__main__':
    main()
