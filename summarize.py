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
        "1m": now - timedelta(days=30),
        "3m": now - timedelta(days=90)
    }

def load_hourly_keyword_counts(since_timestamp):
    """指定されたタイムスタンプ以降の hourly_keyword_counts をロードする"""
    all_hourly_counts = []
    if not os.path.exists(HOURLY_KEYWORD_COUNTS_LOG):
        print(f"Warning: {HOURLY_KEYWORD_COUNTS_LOG} not found.") # ★デバッグ情報
        return all_hourly_counts

    print(f"Loading hourly keyword counts since: {since_timestamp.isoformat()}") # ★デバッグ情報
    min_timestamp_loaded = None # ★デバッグ情報
    max_timestamp_loaded = None # ★デバッグ情報
    entry_count = 0 # ★デバッグ情報

    with open(HOURLY_KEYWORD_COUNTS_LOG, 'r', encoding='utf-8') as f:
        for line_number, line in enumerate(f, 1): # ★デバッグ情報: 行番号追加
            try:
                entry = json.loads(line)
                entry_timestamp_str = entry.get('timestamp') # ★堅牢性: timestampキー存在確認
                if not entry_timestamp_str:
                    print(f"Warning: Line {line_number} in {HOURLY_KEYWORD_COUNTS_LOG} has no 'timestamp'. Skipping.")
                    continue

                entry_timestamp = datetime.fromisoformat(entry_timestamp_str)
                
                if entry_timestamp >= since_timestamp:
                    all_hourly_counts.append(entry)
                    entry_count += 1 # ★デバッグ情報
                    if min_timestamp_loaded is None or entry_timestamp < min_timestamp_loaded: # ★デバッグ情報
                        min_timestamp_loaded = entry_timestamp
                    if max_timestamp_loaded is None or entry_timestamp > max_timestamp_loaded: # ★デバッグ情報
                        max_timestamp_loaded = entry_timestamp
            except json.JSONDecodeError:
                print(f"Warning: Line {line_number} in {HOURLY_KEYWORD_COUNTS_LOG} is not valid JSON. Skipping.") # ★デバッグ情報
                continue
            except KeyError: # 'sources' など他のキーがない場合も考慮
                print(f"Warning: Line {line_number} in {HOURLY_KEYWORD_COUNTS_LOG} has missing keys. Entry: {line.strip()}. Skipping.")
                continue
            except Exception as e: # その他の予期せぬエラー
                 print(f"Warning: Error processing line {line_number} in {HOURLY_KEYWORD_COUNTS_LOG}: {e}. Entry: {line.strip()}. Skipping.")
                 continue


    # ★★★ ここからデバッグ情報出力 ★★★
    print(f"Finished loading {HOURLY_KEYWORD_COUNTS_LOG}.")
    print(f"Total entries loaded: {entry_count}")
    if min_timestamp_loaded and max_timestamp_loaded:
        print(f"Timestamp range of loaded entries: FROM {min_timestamp_loaded.isoformat()} TO {max_timestamp_loaded.isoformat()}")
        time_diff_hours = (max_timestamp_loaded - min_timestamp_loaded).total_seconds() / 3600
        print(f"This covers a period of approximately {time_diff_hours:.2f} hours.")
    elif entry_count > 0:
        print(f"Loaded {entry_count} entries, but could not determine precise timestamp range (possibly single entry or all same timestamp).")
    else:
        print("No entries were loaded for the specified period.")
    # ★★★ ここまでデバッグ情報出力 ★★★
    
    return all_hourly_counts

def aggregate_trends(hourly_counts_data, time_ranges):
    aggregated_data = {period: {"Total": {}} for period in time_ranges}
    
    # ★★★ デバッグ情報: 集計対象となるデータの最初と最後のエントリのタイムスタンプを表示 ★★★
    if hourly_counts_data:
        first_entry_ts = hourly_counts_data[0].get('timestamp', 'N/A')
        last_entry_ts = hourly_counts_data[-1].get('timestamp', 'N/A')
        print(f"Aggregating trends from {len(hourly_counts_data)} hourly entries.")
        print(f"Timestamp of first entry for aggregation: {first_entry_ts}")
        print(f"Timestamp of last entry for aggregation: {last_entry_ts}")
    else:
        print("No hourly data provided for aggregation.")
    # ★★★ ここまで ★★★

    for entry in hourly_counts_data:
        entry_timestamp_str = entry.get('timestamp')
        if not entry_timestamp_str: continue # 念のため
        entry_timestamp = datetime.fromisoformat(entry_timestamp_str)
        
        for period, start_time in time_ranges.items():
            if entry_timestamp >= start_time:
                for source_name, source_counts in entry.get('sources', {}).items():
                    for keyword, count in source_counts.items():
                        aggregated_data[period]["Total"][keyword] = \
                            aggregated_data[period]["Total"].get(keyword, 0) + count
                        
                        if source_name not in aggregated_data[period]:
                            aggregated_data[period][source_name] = {}
                        aggregated_data[period][source_name][keyword] = \
                            aggregated_data[period][source_name].get(keyword, 0) + count
    
    # ★★★ デバッグ情報: 各集計期間で実際にデータがあったか（Totalが空でないか）を表示 ★★★
    for period, data in aggregated_data.items():
        if not data["Total"]:
            print(f"Note: No data found for period '{period}' during aggregation.")
        else:
            print(f"Data aggregated for period '{period}'. Top 3 keywords (Total): {sorted(data['Total'].items(), key=lambda item: item[1], reverse=True)[:3]}")
    # ★★★ ここまで ★★★

    return aggregated_data

def save_daily_trends_to_db(trends_data, current_time):
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

        today_date_str = current_time.strftime('%Y-%m-%d')
        print(f"Deleting existing daily trends for {today_date_str}...")
        cursor.execute('''
            DELETE FROM daily_trends WHERE date = ?
        ''', (today_date_str,))
        conn.commit()
        deleted_rows = cursor.rowcount # ★デバッグ情報
        print(f"Finished deleting {deleted_rows} rows for {today_date_str}.") # ★デバッグ情報

        print("Inserting new daily trends...")
        inserted_row_count = 0 # ★デバッグ情報
        for trend_type, periods_data in trends_data.items():
            for source_name, keywords_counts in periods_data.items():
                for keyword, count in keywords_counts.items():
                    cursor.execute('''
                        INSERT INTO daily_trends (trend_type, source_name, keyword, count, date)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (trend_type, source_name, keyword, count, today_date_str))
                    inserted_row_count += 1 # ★デバッグ情報
        conn.commit()
        print(f"Saved {inserted_row_count} new daily trend entries to DB.") # ★デバッグ情報
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

def generate_individual_summary_report(period_key, period_data, display_limit):
    report_parts = []
    if not period_data.get("Total"): # Totalにデータがなければその期間はデータなし
        print(f"Report generation: No 'Total' data for period {period_key}. Report will be empty for this period.") # ★デバッグ情報
        return "" # 空のレポートを返す

    report_parts.append(f"### 過去 {period_key} のトレンド")
    report_parts.append("**全体:**")
    total_keywords = sorted(
        period_data["Total"].items(), 
        key=lambda item: item[1], 
        reverse=True
    )[:display_limit]
    
    if total_keywords:
        report_parts.append(", ".join([f"{keyword}: {count}件" for keyword, count in total_keywords])) # ★修正: カンマの後にスペース
    else:
        report_parts.append("トレンドなし")
    report_parts.append("")

    sorted_sources = sorted([s for s in period_data.keys() if s != "Total"])
    for source_name in sorted_sources:
        if not period_data[source_name]: # ソース別データが空ならスキップ
            print(f"Report generation: No data for source '{source_name}' in period {period_key}.") # ★デバッグ情報
            continue
            
        source_counts = sorted(
            period_data[source_name].items(),
            key=lambda item: item[1],
            reverse=True
        )[:display_limit]
        
        report_parts.append(f"**{source_name}:**")
        if source_counts:
            report_parts.append(", ".join([f"{keyword}: {count}件" for keyword, count in source_counts])) # ★修正: カンマの後にスペース
        else:
            report_parts.append("トレンドなし")
        report_parts.append("")
    report_parts.append("---\n") 
    return "\n".join(report_parts)

if __name__ == "__main__":
    now_utc = get_utc_now()
    time_ranges = calculate_time_ranges(now_utc)
    
    # 最も古い集計開始時刻を取得 (3ヶ月前)
    earliest_start_time = min(time_ranges.values())
    print(f"Summarize script started. Current UTC: {now_utc.isoformat()}") # ★デバッグ情報
    print(f"Earliest data needed since: {earliest_start_time.isoformat()}") # ★デバッグ情報
    
    hourly_counts = load_hourly_keyword_counts(earliest_start_time)
    
    if not hourly_counts: # ★デバッグ情報
        print("No hourly counts were loaded. Aggregation might result in empty trends.")
        
    trends = aggregate_trends(hourly_counts, time_ranges)
    
    save_daily_trends_to_db(trends, now_utc)
    
    # レポート生成 (getの第2引数に空辞書を指定して、キーが存在しない場合のエラーを回避)
    report_24h = generate_individual_summary_report("24h", trends.get("24h", {}), 10)
    report_1m = generate_individual_summary_report("1m", trends.get("1m", {}), 10)
    report_3m = generate_individual_summary_report("3m", trends.get("3m", {}), 10)

    final_output = []
    final_output.append(f"Aggregating daily trends up to {now_utc.isoformat()}...")
    # DBへの保存メッセージはsave_daily_trends_to_db内で出力されるのでここでは省略
    # final_output.append("Saved daily counts to DB.\n") 
    final_output.append("---REPORT_SPLIT---24H\n")
    final_output.append(report_24h if report_24h.strip() else "24hトレンドデータなし\n") # ★修正: 空の場合のメッセージ
    final_output.append("---REPORT_SPLIT---1MON\n")
    final_output.append(report_1m if report_1m.strip() else "1ヶ月トレンドデータなし\n") # ★修正: 空の場合のメッセージ
    final_output.append("---REPORT_SPLIT---3MON\n")
    final_output.append(report_3m if report_3m.strip() else "3ヶ月トレンドデータなし\n") # ★修正: 空の場合のメッセージ

    print("\n".join(final_output))
