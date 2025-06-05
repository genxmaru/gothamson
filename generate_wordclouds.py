import sqlite3
import os
import json
from wordcloud import WordCloud
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager # ★フォントマネージャーをインポート
from datetime import datetime, timedelta, timezone
# import japanize_matplotlib # ← 今回は一旦コメントアウトし、直接指定で試します

KEYWORD_TRENDS_DB = os.path.join(os.path.dirname(__file__), 'data', 'keyword_trends.db')
WORDCLOUD_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'data', 'wordclouds')

# ★★★ フォントパスの取得処理を変更 ★★★
def get_japanese_font_path():
    # システムにインストールされているフォントからIPA Pゴシックを探す
    font_paths = font_manager.findSystemFonts(fontpaths=None, fontext='ttf')
    # 'ipagp.ttf' (IPA P Gothic) を優先的に探す
    for path in font_paths:
        if 'ipagp.ttf' in path.lower():
            print(f"Found IPA P Gothic (ipagp.ttf) at: {path}")
            return path
    # 見つからなければ 'ipag.ttf' (IPA Gothic) を探す
    for path in font_paths:
        if 'ipag.ttf' in path.lower():
            print(f"Found IPA Gothic (ipag.ttf) at: {path}")
            return path
    # それでも見つからなければ、fc-listでヒットした一般的な日本語フォントパスの候補
    # (ただし、fc-listの結果とfont_managerが返すパスは必ずしも一致しない)
    # news.ymlのfc-cache -fvの後なので、システムは認識しているはず
    default_paths = [
        '/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf',
        '/usr/share/fonts/truetype/fonts-japanese-gothic.ttf'
    ]
    for path in default_paths:
        if os.path.exists(path):
            print(f"Using fallback Japanese font: {path}")
            return path
            
    print("Warning: Japanese font not found. WordCloud may not display Japanese characters correctly.")
    return None # 見つからなければNoneを返す

FONT_PATH = get_japanese_font_path()
# ★★★ ここまで ★★★

def get_latest_trends(db_path, trend_type, source_name):
    # (この関数の中身は変更なし)
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

    font_path_to_use = FONT_PATH
    if not font_path_to_use: # FONT_PATHがNone（見つからなかった）場合
        print(f"Error: Japanese font path could not be determined. Attempting with default font (may cause garbled characters).")
        # font_path=None とするとwordcloudのデフォルトが使われる
    else:
        print(f"Generating word cloud for '{title}' with font: {font_path_to_use}")

    try:
        wc = WordCloud(
            font_path=font_path_to_use, 
            background_color="white",
            max_words=100,
            width=1200,
            height=600,
            collocations=False,
            random_state=42,
            # matplotlibの警告を抑制するために、font_pathがNoneでもエラーにならないようにする
            # ただし、その場合は文字化けする
            stopwords=set() # 必要ならストップワードを設定
        )
        wc.generate_from_frequencies(keywords_data)
        plt.figure(figsize=(12, 6))
        plt.imshow(wc, interpolation='bilinear')
        plt.axis("off")
        # plt.title() は japanize_matplotlib を使わない場合、別途フォント指定が必要
        # 今回はWordCloudライブラリのフォント指定に注力
        if font_path_to_use:
            prop = font_manager.FontProperties(fname=font_path_to_use)
            plt.title(title, fontsize=16, fontproperties=prop)
        else:
            plt.title(title, fontsize=16) # フォント指定なし (文字化けの可能性)

        plt.tight_layout(pad=0)
        os.makedirs(WORDCLOUD_OUTPUT_DIR, exist_ok=True)
        plt.savefig(output_filepath, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"Generated word cloud: {output_filepath}")
    except Exception as e:
        print(f"Error generating word cloud for '{title}': {e}")
        if font_path_to_use and ("cannot open resource" in str(e) or "କ୍ଷ" in str(e)):
             print(f"This might be an issue with the font file at '{font_path_to_use}'.")

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
