import sqlite3
import os
import json # jsonモジュールをインポート
from wordcloud import WordCloud
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone

# ログファイルとDBファイルのパス
KEYWORD_TRENDS_DB = os.path.join(os.path.dirname(__file__), 'data', 'keyword_trends.db')
WORDCLOUD_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'wordclouds')

# 日本語フォントのパス (GitHub ActionsのUbuntu環境で利用可能なフォント)
# IPAexゴシックは多くのLinux環境で利用可能
# 環境によっては以下を試す
# FONT_PATH = '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf' # 汎用的なフォント
# FONT_PATH = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc' # Noto Sans CJK
FONT_PATH = '/usr/share/fonts/opentype/ipaexfont-gothic/ipaexg.ttf' 


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
        # dateカラムで降順にソートし、最初の行を取得することで最新の日付を取得
        cursor.execute('''
            SELECT keyword, count
            FROM daily_trends
            WHERE trend_type = ? AND source_name = ? AND date = (
                SELECT MAX(date) FROM daily_trends WHERE trend_type = ? AND source_name = ?
            )
            ORDER BY count DESC
            LIMIT 100 # ワードクラウドに表示するキーワード数。多すぎると見づらくなる。
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
    # 背景色、最大単語数、フォントパスなどを指定
    wc = WordCloud(
        font_path=FONT_PATH,
        background_color="white",
        max_words=100, # 表示する最大単語数 (get_latest_trendsのLIMITと合わせるか、それより少なく)
        width=1200,    # 画像の幅
        height=600,    # 画像の高さ
        collocations=False, # 複数単語の組み合わせを生成しない（単一キーワードのトレンドなので）
        random_state=42 # 再現性のため
    )

    # ワードクラウドを生成
    wc.generate_from_frequencies(keywords_data)

    # 生成されたワードクラウドを画像として保存
    plt.figure(figsize=(12, 6)) # figsizeもWordCloudのwidth/heightと合わせる
    plt.imshow(wc, interpolation='bilinear')
    plt.axis("off") # 軸を表示しない
    plt.title(title, fontsize=16) # タイトル
    plt.tight_layout(pad=0) # 余白をなくす
    
    # 出力ディレクトリが存在しない場合は作成
    os.makedirs(WORDCLOUD_OUTPUT_DIR, exist_ok=True)
    plt.savefig(output_filepath, dpi=300, bbox_inches='tight') # 高解像度で保存
    plt.close() # メモリ解放のためプロットを閉じる
    print(f"Generated word cloud: {output_filepath}")


if __name__ == "__main__":
    now_utc = datetime.now(timezone.utc)
    # UTCの今日の00:00:00を基準日とする
    today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    date_str = today_utc.strftime('%Y%m%d') # ファイル名に使う日付文字列

    # 集計するトレンドタイプとソース
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
            # DBからキーワードデータを取得
            keywords_data = get_latest_trends(KEYWORD_TRENDS_DB, trend_type_key, source_name_key)
            
            # ファイル名を生成 (例: wordcloud_24h_Total_20240527.png)
            # ファイル名に使えない文字を置換し、小文字に統一
            safe_source_name = source_name_key.replace(" ", "_").replace(".", "").lower() 
            output_filename = f"wordcloud_{trend_type_key}_{safe_source_name}_{date_str}.png"
            output_filepath = os.path.join(WORDCLOUD_OUTPUT_DIR, output_filename)
            
            # ワードクラウドを生成
            title = f"{trend_type_title}: {source_name_title}"
            generate_wordcloud(keywords_data, title, output_filepath)
            
            if keywords_data: # データが生成された場合のみパスを追加
                generated_image_paths.append(output_filepath)
    
    # 生成された画像のパスをGitHub Actionsの出力として設定
    # GitHub ActionsのStep OutputにJSON文字列を書き込む
    # GITHUB_OUTPUTへの書き込み形式は "name=value"
    # ここでは改行文字を含まないよう、1行でJSON文字列を渡す
    print(f"wordcloud_paths={json.dumps(generated_image_paths)}")
