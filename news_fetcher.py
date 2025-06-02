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
# GitHub ActionsのUbuntu環境でmecab-ipadic-utf8がインストールされる標準的なパスを指定
MECAB_DIC_PATH = "/usr/share/mecab/dic/ipadic"  # ★★★ 修正点: 正しい辞書パスに変更しました ★★★

# mecabrcの設定ファイルパス (GitHub ActionsのUbuntu環境のデフォルト)
# `mecabrc`は`/etc/mecabrc`に存在すると考えられる (今回は -r /dev/null で無視するため影響は少ない)
MECABRC_SYSTEM_PATH = "/etc/mecabrc"

try:
    # MeCab辞書パスを明示的に指定して初期化
    # -r /dev/null オプションでシステム全体のmecabrcを無視します。
    #   GitHub Actionsの `news.yml` で辞書ディレクトリ直下に `dicrc` を作成しているため、
    #   MeCabは指定された辞書パス (-d オプション) を見て `dicrc` を読み込みます。
    tagger = MeCab.Tagger(f"-r /dev/null -d {MECAB_DIC_PATH}")
except RuntimeError as e:
    print(f"Failed to initialize MeCab with specified path: {MECAB_DIC_PATH}")
    print("Please verify the MeCab dictionary path and installation based on the provided research.")
    # エラーメッセージに詳細な情報が含まれているので、それも出力するとデバッグに役立ちます。
    print(f"MeCab Error Details: {e}")
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
    os.makedirs(os.path.dirname(PROCESSED_ARTICLES_LOG), exist_ok=True) # dataディレクトリ作成
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
                    print(f"Warning: Skipping malformed JSON line in {HOURLY_KEYWORD_COUNTS_LOG}: {line.strip()}")
                    continue # 不正な行はスキップ
                except KeyError:
                    print(f"Warning: Skipping entry with missing 'timestamp' in {HOURLY_KEYWORD_COUNTS_LOG}: {line.strip()}")
                    continue # timestampがないエントリはスキップ


    # dataディレクトリが存在しない場合は作成
    os.makedirs(os.path.dirname(HOURLY_KEYWORD_COUNTS_LOG), exist_ok=True)

    with open(temp_log_path, 'w', encoding='utf-8') as f_tmp:
        for entry_line in retained_entries:
            f_tmp.write(entry_line)
    
    # HOURLY_KEYWORD_COUNTS_LOG が存在しない場合でもreplaceはエラーになる可能性がある
    if os.path.exists(HOURLY_KEYWORD_COUNTS_LOG) or retained_entries:
        os.replace(temp_log_path, HOURLY_KEYWORD_COUNTS_LOG)
    elif os.path.exists(temp_log_path): # 元ファイルがなく、保持エントリもないがtmpファイルが作られた場合
        os.remove(temp_log_path)

    print(f"Cleaned {HOURLY_KEYWORD_COUNTS_LOG}. Retained {len(retained_entries)} entries.")

def fetch_and_log_keywords():
    """RSSフィードからニュース記事をフェッチし、キーワードを抽出し、ログに追記する"""
    print(f"Fetching news at {datetime.now(timezone.utc)}...")
    processed_urls = load_processed_articles()
    new_processed_urls = list(processed_urls) # 新しい処理済みURLリストをコピーして作成
    
    current_hourly_counts = {"timestamp": datetime.now(timezone.utc).isoformat(), "sources": {}}
    new_keywords_detected = False

    for source_name, rss_url in RSS_FEEDS.items():
        print(f"Processing feed: {source_name} ({rss_url})")
        try:
            feed = feedparser.parse(rss_url)
            source_keyword_counts = Counter()
            
            for entry in feed.entries:
                link = entry.link
                if link not in processed_urls: # setにすると検索が高速だが、今回はリストのままでも問題ない量と想定
                    try:
                        print(f"Fetching article: {link}")
                        response = requests.get(link, timeout=10)
                        response.raise_for_status()
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        text_content = ""
                        # 主要な記事本文が含まれそうなセレクタのリスト
                        # より多くのサイトに対応するため、一般的なクラス名や要素名を追加/調整可能
                        selectors = [
                            'article', '.entry-content', '.post-content', '.article-body', 
                            '.story-content', '.main-content', '.news-text', '.article_body',
                            '.content__body', '.zn-body__paragraph', 'div[itemprop="articleBody"]'
                        ]
                        for selector in selectors:
                            body_div = soup.select_one(selector) # select_oneで見つかった最初の要素を取得
                            if body_div:
                                text_content = body_div.get_text(separator=' ', strip=True)
                                break
                        
                        if not text_content: # 上記セレクタで見つからなければdescription/summaryを試す
                            text_content = entry.get('description', entry.get('summary', ''))
                            text_content = BeautifulSoup(text_content, 'html.parser').get_text(separator=' ', strip=True)


                        if text_content:
                            print(f"Extracting keywords from: {link}")
                            keywords = extract_keywords(text_content)
                            if keywords:
                                print(f"Detected keywords: {keywords[:5]}...") # 最初の5件程度表示
                                source_keyword_counts.update(keywords)
                                new_keywords_detected = True
                        else:
                            print(f"No text content found for: {link}")
                        
                        new_processed_urls.append(link)
                    except requests.exceptions.RequestException as e:
                        print(f"Error fetching article {link}: {e}")
                    except Exception as e:
                        print(f"Error processing article {link}: {e}") # より詳細なエラー出力
            
            if source_keyword_counts:
                current_hourly_counts["sources"][source_name] = dict(source_keyword_counts)

        except Exception as e:
            print(f"Warning: Could not parse feed {rss_url} - {e}")

    if new_keywords_detected:
        # dataディレクトリが存在しない場合は作成
        os.makedirs(os.path.dirname(HOURLY_KEYWORD_COUNTS_LOG), exist_ok=True)
        with open(HOURLY_KEYWORD_COUNTS_LOG, 'a', encoding='utf-8') as f:
            json.dump(current_hourly_counts, f, ensure_ascii=False)
            f.write('\n')
        print("New keywords detected and logged.")
    else:
        print("No new keywords detected in this run.")

    save_processed_articles(new_processed_urls)
    print("Updated processed_articles.json.")

if __name__ == "__main__":
    # dataディレクトリの存在確認と作成 (念のため)
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(data_dir, exist_ok=True)
    config_dir = os.path.join(os.path.dirname(__file__), 'config') # configディレクトリも
    os.makedirs(config_dir, exist_ok=True)


    # 初回実行時などに keywords.json がないと EXCLUDE_KEYWORDS が正しくロードされないため、
    # ダミーの config/keywords.json を作成する処理を追加 (存在しない場合のみ)
    if not os.path.exists(CONFIG_KEYWORDS_PATH):
        print(f"{CONFIG_KEYWORDS_PATH} not found. Creating a dummy file.")
        with open(CONFIG_KEYWORDS_PATH, 'w', encoding='utf-8') as f_cfg:
            json.dump({"exclude_keywords": ["example_exclude_word"]}, f_cfg, indent=4)


    clean_hourly_keyword_counts_log(max_age_hours=25) # デフォルト25時間保持
    fetch_and_log_keywords()
