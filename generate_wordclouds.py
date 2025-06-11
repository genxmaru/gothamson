import sqlite3
import os
import json
from wordcloud import WordCloud
from datetime import datetime, timezone, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

KEYWORD_TRENDS_DB = os.path.join(os.path.dirname(__file__), 'data', 'keyword_trends.db')
WORDCLOUD_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'data', 'wordclouds')

# --- 日本語フォントパスを取得 ---
# news.yml で fonts-ipafont-gothic をインストールしているので、そのパスを指定
# fc-list の結果と generate_wordclouds.py の実行ログから、以下のパスに存在することを確認済み
FONT_PATH = '/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf'

def get_latest_trends(db_path, trend_type, source_name):
    conn = None
    keywords_data = {}
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
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
    if not keywords_data:
        print(f"No data for '{title}', skipping word cloud generation.")
        return

    # フォントパスの存在確認
    if not os.path.exists(FONT_PATH):
        print(f"Error: Font file NOT FOUND at {FONT_PATH}. Word cloud cannot be generated with Japanese characters.")
        # フォントが見つからない場合は、警告を出して処理を中断するか、
        # または英語のみのフォントで生成を試みる（推奨されない）
        # ここでは、日本語表示が目的なので、エラーとして扱うか、
        # wordcloud ライブラリのデフォルトフォント（英語のみ）で生成を試みる。
        # 今回は、エラーを出さずにデフォルトフォントで試行する（ただし文字化け警告は出る）
        font_to_use = None 
        print(f"Attempting to generate word cloud with default font (may cause garbled Japanese characters).")
    else:
        font_to_use = FONT_PATH
        print(f"Generating word cloud for '{title}' with font: {font_to_use}")

    try:
        wordcloud = WordCloud(
            font_path=font_to_use, # ★★★ 必ずこのパスが使われるようにする ★★★
            background_color="white",
            max_words=100,
            width=1200,
            height=600,
            collocations=False,
            random_state=42,
            stopwords=set() 
        ).generate_from_frequencies(keywords_data)

        plt.figure(figsize=(12, 6))
        plt.imshow(wordcloud, interpolation='bilinear')
        plt.axis("off")

        # matplotlibのタイトルにも日本語フォントを適用 (japanize-matplotlib が確実)
        # ただし、japanize_matplotlib を import していない場合は、個別にFontPropertiesで指定
        if font_to_use:
            try:
                # japanize_matplotlib があれば、これだけでタイトルも日本語化されるはず
                import japanize_matplotlib 
                plt.title(title, fontsize=16)
            except ImportError:
                # japanize_matplotlib がない場合は、FontPropertiesで試みる
                print("japanize-matplotlib not found, trying FontProperties for title.")
                font_prop = font_manager.FontProperties(fname=font_to_use)
                plt.title(title, fontsize=16, fontproperties=font_prop)
        else: # フォントパスがなければデフォルト (英語のみ)
             plt.title(title, fontsize=16)

        plt.tight_layout(pad=0)
        os.makedirs(WORDCLOUD_OUTPUT_DIR, exist_ok=True)
        plt.savefig(output_filepath, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"Generated word cloud: {output_filepath}")

    except Exception as e:
        print(f"Error generating word cloud for '{title}': {e}")
        if font_to_use and ("cannot open resource" in str(e).lower() or "unknown font format" in str(e).lower()):
             print(f"Critical Error: The font file at '{font_to_use}' could not be opened or is not a valid font file.")
        elif "Glyph" in str(e) and "missing from font(s)" in str(e):
             print(f"Warning: Some characters were missing from the font. This might be okay if they are not Japanese characters.")


if __name__ == "__main__":
    # (この部分も変更なし)
    now_utc = datetime.now(timezone.utc)
    date_str = now_utc.strftime('%Y%m%d')
    trend_types = {
        "24h": "過去24時間のトレンド",
        "1m": "過去1ヶ月のトレンド",
        "3m": "過去3ヶ月のトレンド"
    }
    source_names_map = {
        "Total": "全体",
        "Cointelegraph": "Cointelegraph",
        "CryptoNews": "CryptoNews",
        "Bitcoin.com News": "Bitcoin.com News",
        "Decrypt": "Decrypt"
    }
    generated_image_paths = []
    for trend_type_key, trend_type_title_jp in trend_types.items():
        for source_name_db, source_name_title_jp in source_names_map.items():
            print(f"Fetching data for: Trend={trend_type_key}, Source={source_name_db}")
            keywords_data = get_latest_trends(KEYWORD_TRENDS_DB, trend_type_key, source_name_db)
            if not keywords_data:
                print(f"No keywords data found for Trend={trend_type_key}, Source={source_name_db}. Skipping word cloud.")
                continue
            safe_source_name = source_name_db.replace(" ", "_").replace(".", "").lower()
            output_filename = f"wordcloud_{trend_type_key}_{safe_source_name}_{date_str}.png"
            output_filepath = os.path.join(WORDCLOUD_OUTPUT_DIR, output_filename)
            title_for_wc = f"{trend_type_title_jp}: {source_name_title_jp} ({date_str})"
            generate_wordcloud(keywords_data, title_for_wc, output_filepath)
            if os.path.exists(output_filepath):
                generated_image_paths.append(output_filepath)
            else:
                print(f"Warning: Word cloud image was not generated at {output_filepath}")
    if generated_image_paths:
        print("\nSuccessfully generated word clouds:")
        for path in generated_image_paths:
            print(path)
    else:
        print("\nNo word clouds were generated in this run.")
