import sqlite3
import os
import json
from wordcloud import WordCloud
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone

# ログファイルとDBファイルのパス
KEYWORD_TRENDS_DB = os.path.join(os.path.dirname(__file__), 'data', 'keyword_trends.db')
WORDCLOUD_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'data', 'wordclouds')

# 日本語フォントのパス (GitHub ActionsのUbuntu環境で利用可能なフォント)
# 前回、一時的な切り分け策として汎用フォントを提案したが、
# 今回は問題の切り分けと解決を最優先するため、最も確実性の高いパスに固定する。
# IPAex Gothicのパスは `/usr/share/fonts/opentype/ipaexfont-gothic/ipaexg.ttf` であり、
# もしこれで動かない場合は、GitHub Actions環境の根本的な問題か、
# WordCloud/Pillowライブラリの特定バージョンとの相性問題が考えられる。
FONT_PATH = '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf' # 汎用フォントでまず動作確認

def get_latest_trends(db_path, trend_type, source_name):
    """
    指定されたトレンドタイプとソース名の最新のキーワードトレンドデータをDBから取得する
    """
    conn = None
    keywords_data = {}
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 最新のデータ（最も新しい日付のデータ）を取得
        cursor.execute('''
            SELECT keyword, count
            FROM daily_trends
            WHERE trend_type = ? AND source_name = ? AND date = (
                SELECT MAX(date) FROM daily_trends WHERE trend_type = ? AND source_name = ?
            )
            ORDER BY count DESC
            LIMIT 100
        ''', (trend_type, source_name, trend_type, source_name))
        
        for keyword, count in cursor.fetchall():
            keywords_data[keyword] = count
    except sqlite3.Error as e:
        print(f"Database error when fetching trends for {trend_type}, {source_name}: {e}")
    finally:
        if conn:
            conn.close()
    return keywords_data

def generate_wordcloud(keywords_data, title, output_filepath):
    """
    キーワードデータからワードクラウドを生成し、画像として保存する
    """
    if not keywords_data:
        print(f"No data for {title}, skipping word cloud generation.")
        return

    # WordCloudオブジェクトの設定
    wc = WordCloud(
        font_path=FONT_PATH,
        background_color="white",
        max_words=100,
        width=1200,
        height=600,
        collocations=False,
        random_state=42
    )

    # ワードクラウドを生成
    wc.generate_from_frequencies(keywords_data)

    # 生成されたワードクラウドを画像として保存
    plt.figure(figsize=(12, 6))
    plt.imshow(wc, interpolation='bilinear')
    plt.axis("off")
    plt.title(title, fontsize=16)
    plt.tight_layout(pad=0)
    
    # 出力ディレクトリが存在しない場合は作成
    os.makedirs(WORDCLOUD_OUTPUT_DIR, exist_ok=True)
    plt.savefig(output_filepath, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Generated word cloud: {output_filepath}")


if __name__ == "__main__":
    now_utc = datetime.now(timezone.utc)
    today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    date_str = today_utc.strftime('%Y%m%d')

    trend_types = {
        "24h": "過去24時間のトレンド",
        "1m": "過去1ヶ月のトレンド",
        "3m": "過去3ヶ月のトレンド"
    }
    source_names = {
        "Total": "全体",
        "Bitcoin.com News": "Bitcoin.com News",
        "Cointelegraph": "Cointelegraph",
        "CryptoNews": "CryptoNews",
        "Decrypt": "Decrypt"
    }

    generated_image_paths = []

    for trend_type_key, trend_type_title in trend_types.items():
        for source_name_key, source_name_title in source_names.items():
            keywords_data = get_latest_trends(KEYWORD_TRENDS_DB, trend_type_key, source_name_key)
            
            safe_source_name = source_name_key.replace(" ", "_").replace(".", "").lower()
            output_filename = f"wordcloud_{trend_type_key}_{safe_source_name}_{date_str}.png"
            output_filepath = os.path.join(WORDCLOUD_OUTPUT_DIR, output_filename)
            
            title = f"{trend_type_title}: {source_name_title}"
            generate_wordcloud(keywords_data, title, output_filepath)
            
            if keywords_data:
                generated_image_paths.append(output_filepath)
