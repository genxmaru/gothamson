import json
from collections import Counter
from datetime import datetime, timedelta

LOG_PATH = "data/log.jsonl"

# 過去指定時間内のログを読み込む
def load_recent(hours: int = 24):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    recent = []
    try:
        with open(LOG_PATH, encoding='utf-8') as f:
            for line in f:
                obj = json.loads(line)
                ts = datetime.fromisoformat(obj['timestamp'])
                if ts >= cutoff:
                    recent.append(obj)
        return recent # ここを修正 (tryブロックの中にインデント)
    except FileNotFoundError:
        # ログファイルがない場合は空リストを返却
        return []

# キーワード出現頻度を集計し文字列で返却
def summarize(entries):
    cnt = Counter()
    for e in entries:
        cnt.update(e.get('keywords', []))
    top = cnt.most_common(5)
    if not top:
        return "📊 過去24時間に該当キーワードの記事はありません"
    lines = ["📊 過去24時間のキーワード頻度トップ5"]
    for kw, c in top:
        lines.append(f"- {kw}: {c}件")
    return "\n".join(lines)

if __name__ == '__main__':
    recs = load_recent()
    output = summarize(recs)
    print(output)