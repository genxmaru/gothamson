import sqlite3
from datetime import datetime, timezone

DATABASE_PATH = "data/keyword_trends.db"

def init_db():
    """データベースを初期化し、テーブルを作成する"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # キーワード集計テーブル
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keyword_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            period_type TEXT NOT NULL, -- 'hourly', 'daily', 'weekly', 'monthly'
            keyword TEXT NOT NULL,
            count INTEGER NOT NULL,
            UNIQUE(timestamp, period_type, keyword) -- 同じ期間・同じキーワードの重複を防止
        )
    """)

    conn.commit()
    conn.close()

def insert_keyword_counts(timestamp_utc, period_type, keyword_counts):
    """
    キーワードの出現回数をデータベースに挿入する
    :param timestamp_utc: ISOフォーマットのUTCタイムスタンプ (例: "2023-10-27T10:00:00.000000+00:00")
    :param period_type: 'hourly', 'daily', 'weekly', 'monthly' など
    :param keyword_counts: {keyword: count, ...} の辞書
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    for keyword, count in keyword_counts.items():
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO keyword_counts (timestamp, period_type, keyword, count)
                VALUES (?, ?, ?, ?)
            """, (timestamp_utc, period_type, keyword, count))
        except sqlite3.Error as e:
            print(f"Error inserting data for {keyword}: {e}")
            conn.rollback() # エラーが発生したらロールバック
            break # このトランザクションを中断

    conn.commit()
    conn.close()

def get_keyword_counts(start_time_utc, end_time_utc, period_type='hourly'):
    """
    指定された期間と期間タイプ（hourly, dailyなど）のキーワード集計データを取得する
    :param start_time_utc: 開始UTCタイムスタンプ (datetimeオブジェクト)
    :param end_time_utc: 終了UTCタイムスタンプ (datetimeオブジェクト)
    :param period_type: 'hourly' など
    :return: 取得したデータのリスト
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # datetimeオブジェクトをISOフォーマットの文字列に変換
    start_str = start_time_utc.isoformat()
    end_str = end_time_utc.isoformat()

    cursor.execute("""
        SELECT keyword, count
        FROM keyword_counts
        WHERE timestamp BETWEEN ? AND ? AND period_type = ?
    """, (start_str, end_str, period_type))
    
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_last_processed_timestamp(period_type):
    """
    指定された期間タイプで最後に処理されたタイムスタンプを取得する
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT MAX(timestamp) FROM keyword_counts WHERE period_type = ?
    """, (period_type,))
    result = cursor.fetchone()[0]
    conn.close()
    return datetime.fromisoformat(result).astimezone(timezone.utc) if result else None


if __name__ == '__main__':
    # スクリプトを直接実行してデータベースを初期化する例
    print("Initializing database...")
    init_db()
    print(f"Database initialized at: {DATABASE_PATH}")

    # テストデータの挿入例 (コメントアウトして使用)
    # now = datetime.now(timezone.utc)
    # test_hourly_data = {
    #     "Stablecoin": 5,
    #     "DeFi": 3,
    #     "AI": 1
    # }
    # insert_keyword_counts(now.isoformat(), 'hourly', test_hourly_data)
    # print("Test hourly data inserted.")

    # データの取得例 (コメントアウトして使用)
    # two_hours_ago = now - timedelta(hours=2)
    # recent_data = get_keyword_counts(two_hours_ago, now, 'hourly')
    # print("Recent hourly data:", recent_data)
