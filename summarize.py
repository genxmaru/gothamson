import json
from datetime import datetime, timedelta, timezone
import os
import sqlite3

# ログファイルとDBファイルのパス
HOURLY_KEYWORD_COUNTS_LOG = os.path.join(os.path.dirname(__file__), 'data', 'hourly_keyword_counts.jsonl')
KEYWORD_TRENDS_DB = os.path.join(os.path.dirname(__file__), 'data', 'keyword_trends.db')

def get_utc_now():
    """現在のUTC時刻を取得する"""
    return datetime.now(timezone.utc)

def calculate_time_ranges(now):
    """トレンド集計期間を計算する"""
    return {
        "24h": now - timedelta(hours=24),
        "1m": now - timedelta(days=30),  # 約1ヶ月
        "3m": now - timedelta(days=90)   # 約3ヶ月
    }

def load_hourly_keyword_counts(since_timestamp):
    """指定されたタイムスタンプ以降の hourly_keyword_counts をロードする"""
    all_hourly_counts = []
    if not os.path.exists(HOURLY_KEYWORD_COUNTS_LOG):
        return all_hourly_counts

    with open(HOURLY_KEYWORD_COUNTS_LOG, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                entry = json.loads(line)
                entry_timestamp = datetime.fromisoformat(entry['timestamp'])
                # since_timestampよりも新しいか、同じ時刻のエントリのみを対象とする
                if entry_timestamp >= since_timestamp:
                    all_hourly_counts.append(entry)
            except json.JSONDecodeError:
                continue # 不正な行はスキップ
    return all_hourly_counts

def aggregate_trends(hourly_counts_data, time_ranges):
    """
    時間範囲とソース別にキーワードトレンドを集計する
    """
    aggregated_data = {period: {"Total": {}} for period in time_ranges}

    for entry in hourly_counts_data:
        entry_timestamp = datetime.fromisoformat(entry['timestamp'])
        
        for period, start_time in time_ranges.items():
            if entry_timestamp >= start_time:
                # 全体でのカウントを更新
                for source_name, source_counts in entry.get('sources', {}).items():
                    for keyword, count in source_counts.items():
                        aggregated_data[period]["Total"][keyword] = \
                            aggregated_data[period]["Total"].get(keyword, 0) + count
                        
                        # ソース別のカウントを更新
                        if source_name not in aggregated_data[period]:
                            aggregated_data[period][source_name] = {}
                        aggregated_data[period][source_name][keyword] = \
                            aggregated_data[period][source_name].get(keyword, 0) + count
    
    return aggregated_data

def save_daily_trends_to_db(trends_data, current_time):
    """日次トレンドデータをSQLiteデータベースに保存する"""
    conn = None
    try:
        conn = sqlite3.connect(KEYWORD_TRENDS_DB)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trend_type TEXT NOT NULL,
                source_name TEXT NOT NULL,
                keyword TEXT NOT NULL,
                count INTEGER NOT NULL,
                date TEXT NOT NULL,
                UNIQUE(trend_type, source_name, keyword, date) ON CONFLICT REPLACE
            )
        ''')
        conn.commit()

        # `current_time`のYYYY-MM-DD形式で、その日のすべてのトレンドデータを削除する
        # これにより、毎日新しいデータで完全に置き換えられる
        today_date_str = current_time.strftime('%Y-%m-%d')
        print(f"Deleting existing daily trends for {today_date_str}...")
        cursor.execute('''
            DELETE FROM daily_trends WHERE date = ?
        ''', (today_date_str,))
        conn.commit()
        print(f"Finished deleting for {today_date_str}.")

        # データを挿入
        print("Inserting new daily trends...")
        for trend_type, periods_data in trends_data.items():
            for source_name, keywords_counts in periods_data.items():
                for keyword, count in keywords_counts.items():
                    cursor.execute('''
                        INSERT INTO daily_trends (trend_type, source_name, keyword, count, date)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (trend_type, source_name, keyword, count, today_date_str))
        conn.commit()
        print("Saved new daily counts to DB.")
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

def generate_individual_summary_report(period_key, period_data, display_limit):
    """個別の期間（例: 24h, 1m, 3m）のレポートを生成する"""
    report_parts = []
    
    if not period_data.get("Total"):
        return ""

    report_parts.append(f"### 過去 {period_key} のトレンド")
    
    # 全体でのトレンド
    report_parts.append("**全体:**")
    total_keywords = sorted(
        period_data["Total"].items(), 
        key=lambda item: item[1], 
        reverse=True
    )[:display_limit]
    
    if total_keywords:
        report_parts.append(",".join([f"{keyword}: {count}件" for keyword, count in total_keywords]))
    else:
        report_parts.append("トレンドなし")
    
    report_parts.append("")

    # ソース別のトレンド (Total以外のソースをループ)
    sorted_sources = sorted([s for s in period_data.keys() if s != "Total"])
    for source_name in sorted_sources:
        source_counts = sorted(
            period_data[source_name].items(),
            key=lambda item: item[1],
            reverse=True
        )[:display_limit]
        
        report_parts.append(f"**{source_name}:**")
        if source_counts:
            report_parts.append(",".join([f"{keyword}: {count}件" for keyword, count in source_counts]))
        else:
            report_parts.append("トレンドなし")
        report_parts.append("")
    
    report_parts.append("---\n") 

    return "\n".join(report_parts)


if __name__ == "__main__":
    now_utc = get_utc_now()
    time_ranges = calculate_time_ranges(now_utc)
    
    earliest_start_time = min(time_ranges.values())
    
    hourly_counts = load_hourly_keyword_counts(earliest_start_time)
    
    trends = aggregate_trends(hourly_counts, time_ranges)
    
    save_daily_trends_to_db(trends, now_utc)
    
    report_24h = generate_individual_summary_report("24h", trends.get("24h", {}), 10)
    report_1m = generate_individual_summary_report("1m", trends.get("1m", {}), 10)
    report_3m = generate_individual_summary_report("3m", trends.get("3m", {}), 10)

    final_output = []
    final_output.append(f"Aggregating daily trends up to {now_utc.isoformat()}...")
    final_output.append("Saved daily counts to DB.\n")
    final_output.append("---REPORT_SPLIT---24H\n")
    final_output.append(report_24h)
    final_output.append("---REPORT_SPLIT---1MON\n")
    final_output.append(report_1m)
    final_output.append("---REPORT_SPLIT---3MON\n")
    final_output.append(report_3m)

    print("\n".join(final_output))
