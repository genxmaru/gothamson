import feedparser
from bs4 import BeautifulSoup
import requests
import json
import os
from datetime import datetime, timezone, timedelta
import re
import MeCab
from collections import Counter

# 設定
RSS_FEEDS = {
    "Cointelegraph": "https://cointelegraph.com/rss",
    "CryptoNews": "https://cryptonews.com/feed/",
    "Bitcoin.com News": "https://news.bitcoin.com/feed/",
    "The Block": "https://www.theblockcrypto.com/rss",
    "Decrypt": "https://decrypt.co/feed"
}

# ファイルパス
PROCESSED_ARTICLES_LOG = os.path.join(os.path.dirname(__file__), 'data', 'processed_articles.json')
HOURLY_KEYWORD_COUNTS_LOG = os.path.join(os.path.dirname(__file__), 'data', 'hourly_keyword_counts.jsonl')
CONFIG_KEYWORDS_PATH = os.path.join(os.path.dirname(__file__), 'config', 'keywords.json')

# 除外キーワードをロード
def load_exclude_keywords(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [k.lower() for k in data.get("exclude_keywords", [])]
    return []

EXCLUDE_KEYWORDS = load_exclude_keywords(CONFIG_KEYWORDS_PATH)

# 形態素解析器の初期化 (MeCab)
# GitHub ActionsのUbuntu環境でmecab-ipadic-utf8がインストールされるパスを指定
# ログと経験に基づき、正しい辞書フォルダは /usr/lib/x86_64-linux-gnu/mecab/dic/ipadic である
MECAB_DIC_PATH = "/usr/lib/x86_64-linux-gnu/mecab/dic/ipadic"

try:
    # MeCab辞書パスを明示的に指定して初期化し、mecabrcは無効化する
    # これにより、システム上のmecabrcやdicrcの存在に依存せず、確実に辞書を読み込む
    tagger = MeCab.Tagger(f"-r /dev/null -d {MECAB_DIC_PATH}")
except RuntimeError as e:
    print(f"Failed to initialize MeCab with specified path: {MECAB_DIC_PATH}")
    print("Please verify the MeCab dictionary path and installation based on the provided research.")
    raise # 致命的なエラーとして再スローする


def extract_keywords(text):
    node = tagger.parseToNode(text)
    keywords = []
    while node:
        # 名詞のみを抽出 (一般、固有名詞、動詞の原型など)
        if node.feature.startswith('名詞') or node.feature.startswith('動詞,自立') or node.feature.startswith('形容詞,自立'):
            # 除外キーワードリストに含まれていないか確認
            if node.surface.lower() not in EXCLUDE_KEYWORDS and len(node.surface) > 1: # 1文字のキーワードは除外
                keywords.append(node.surface)
        node = node.next
    return keywords

def load_processed_articles():
    """過去に処理した記事のURLをロードする"""
    if os.path.exists(PROCESSED_ARTICLES_LOG):
        with open(PROCESSED_ARTICLES_LOG, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def save_processed_articles(urls):
    """処理した記事のURLを保存する"""
    with open(PROCESSED_ARTICLES_LOG, 'w', encoding='utf-8') as f:
        json.dump(urls, f, indent=4)

def clean_hourly_keyword_counts_log(max_age_hours=24):
    """
    hourly_keyword_counts.jsonl から古いエントリを削除し、ファイルをクリーンアップする
    """
    print(f"Cleaning {HOURLY_KEYWORD_COUNTS_LOG} for entries older than {max_age_hours} hours.")
    temp_log_path = HOURLY_KEYWORD_COUNTS_LOG + ".tmp"
    
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    
    retained_entries = []
    if os.path.exists(HOURLY_KEYWORD_COUNTS_LOG):
        with open(HOURLY_KEYWORD_COUNTS_LOG, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    entry_timestamp = datetime.fromisoformat(entry['timestamp'])
                    if entry_timestamp >= cutoff_time:
                        retained_entries.append(line)
                except json.JSONDecodeError:
                    continue # 不正な行はスキップ

    with open(temp_log_path, 'w', encoding='utf-8') as f_tmp:
        for entry_line in retained_entries:
            f_tmp.write(entry_line)
    
    os.replace(temp_log_path, HOURLY_KEYWORD_COUNTS_LOG)
    print(f"Cleaned {HOURLY_KEYWORD_COUNTS_LOG}. Retained {len(retained_entries)} entries.")


def fetch_and_log_keywords():
    """RSSフィードからニュース記事をフェッチし、キーワードを抽出し、ログに追記する"""
    print(f"Fetching news at {datetime.now(timezone.utc)}...")
    processed_urls = load_processed_articles()
    new_processed_urls = list(processed_urls)
    
    current_hourly_counts = {"timestamp": datetime.now(timezone.utc).isoformat(), "sources": {}}
    new_keywords_detected = False

    for source_name, rss_url in RSS_FEEDS.items():
        print(f"Processing feed: {source_name} ({rss_url})")
        try:
            feed = feedparser.parse(rss_url)
            source_keyword_counts = Counter()
            
            for entry in feed.entries:
                link = entry.link
                if link not in processed_urls:
                    try:
                        response = requests.get(link, timeout=10)
                        response.raise_for_status()
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        text_content = ""
                        for selector in ['article', '.entry-content', '.post-content', '.article-content', '.news-text']:
                            body_div = soup.find(selector)
                            if body_div:
                                text_content = body_div.get_text()
                                break
                        
                        if not text_content:
                            text_content = entry.get('description', entry.get('summary', ''))

                        keywords = extract_keywords(text_content)
                        if keywords:
                            source_keyword_counts.update(keywords)
                            new_keywords_detected = True
                        
                        new_processed_urls.append(link)
                    except requests.exceptions.RequestException as e:
                        print(f"Error fetching article {link}: {e}")
                    except Exception as e:
                        print(f"Error processing article {link}: { {e}}")
            
            if source_keyword_counts:
                current_hourly_counts["sources"][source_name] = dict(source_keyword_counts)

        except Exception as e:
            print(f"Warning: Could not parse feed {rss_url} - {e}")

    if new_keywords_detected:
        with open(HOURLY_KEYWORD_COUNTS_LOG, 'a', encoding='utf-8') as f:
            json.dump(current_hourly_counts, f, ensure_ascii=False)
            f.write('\n')
        print("New keywords detected and logged.")
    else:
        print("No new keywords detected in this run.")

    save_processed_articles(new_processed_urls)
    print("Updated processed_articles.json.")

if __name__ == "__main__":
    clean_hourly_keyword_counts_log(max_age_hours=25)
    fetch_and_log_keywords()
