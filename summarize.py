import json
from datetime import datetime, timedelta, timezone
from collections import Counter
import os
import db_manager # db_manager.pyをインポート

# --- 設定ファイルのパス ---
KEYWORDS_CONFIG_PATH = "config/keywords.json"

# --- データファイルのパス ---
HOURLY_LOG_PATH = "data/hourly_keyword_counts.jsonl"

# --- Discord通知を生成する関数をインポート (後で作成) ---
# from notification_helper import generate_discord_embed_payload

def load_config(filepath):
    """指定されたJSONファイルを読み込む"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_hourly_logs(start_time_utc):
    """指定された開始時刻以降の時間ごとのキーワードログを読み込む"""
    logs = []
    if not os.path.exists(HOURLY_LOG_PATH):
        return logs

    with open(HOURLY_LOG_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                entry = json.loads(line)
                log_timestamp = datetime.fromisoformat(entry['timestamp']).astimezone(timezone.utc)
                if log_timestamp >= start_time_utc:
                    logs.append(entry)
            except json.JSONDecodeError:
                continue # 不正なJSON行はスキップ
    return logs

def aggregate_keyword_counts(logs):
    """読み込んだログからキーワードの合計出現回数を集計する"""
    total_counts = Counter()
    for log_entry in logs:
        if 'keyword_counts' in log_entry:
            for keyword, count in log_entry['keyword_counts'].items():
                total_counts[keyword] += count
    return total_counts

def get_top_keywords_text(aggregated_counts, num_top=10):
    """集計されたキーワードからトップNを整形して返す"""
    if not aggregated_counts:
        return "該当期間のキーワードはありません。"

    lines = []
    for keyword, count in aggregated_counts.most_common(num_top):
        lines.append(f"- {keyword}: {count}件")
    return "\n".join(lines)

def get_trend_summary(period_hours, keywords_list):
    """
    指定された期間のキーワード集計を行い、データベースに保存し、通知テキストを生成する。
    """
    now_utc = datetime.now(timezone.utc)
    start_time_utc = now_utc - timedelta(hours=period_hours)
    period_type_str = ""
    if period_hours == 24:
        period_type_str = "daily"
    elif period_hours == 24 * 7:
        period_type_str = "weekly"
    elif period_hours == 24 * 30: # 約1ヶ月
        period_type_str = "monthly"
    else:
        period_type_str = f"{period_hours}h"

    print(f"Aggregating {period_type_str} trends from {start_time_utc} to {now_utc}...")

    hourly_logs = load_hourly_logs(start_time_utc)
    aggregated_counts = aggregate_keyword_counts(hourly_logs)

    # データベースに保存
    db_manager.insert_keyword_counts(now_utc.isoformat(), period_type_str, aggregated_counts)
    print(f"Saved {period_type_str} counts to DB.")

    # Discord通知用のテキストを生成
    title_prefix = {
        "daily": "過去24時間のトレンド",
        "weekly": "過去1週間のトレンド",
        "monthly": "過去1ヶ月のトレンド"
    }.get(period_type_str, f"過去{period_hours}時間のトレンド")

    summary_text = f"### {title_prefix}\n"
    summary_text += get_top_keywords_text(aggregated_counts, num_top=10) # トップ10キーワードを表示

    return summary_text

if __name__ == '__main__':
    # データベースの初期化を確認（既に存在すればスキップされる）
    db_manager.init_db()

    # 各期間の集計と通知テキスト生成
    # (ワークフローのトリガーに合わせて実行する期間を決定)

    # 例: 手動実行時や毎日実行時に日次レポートを生成
    daily_summary = get_trend_summary(24, load_config(KEYWORDS_CONFIG_PATH))
    print("\n" + daily_summary)

    # 例: 手動実行時や毎週実行時に週次レポートを生成
    # weekly_summary = get_trend_summary(24 * 7, load_config(KEYWORDS_CONFIG_PATH))
    # print("\n" + weekly_summary)

    # 例: 手動実行時や毎月実行時に月次レポートを生成
    # monthly_summary = get_trend_summary(24 * 30, load_config(KEYWORDS_CONFIG_PATH))
    # print("\n" + monthly_summary)

    # --- Discord通知の実行は、workflow_dispatchまたはcronジョブに紐付けて行われます ---
    # 実際には、このスクリプトが生成したテキストをワークフローのCurlコマンドで送信します。
    # generate_discord_embed_payload関数はnotification_helper.pyで定義し、ここでインポートして使用します。
