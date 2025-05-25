import json

def generate_discord_embed_payload(title, description, color=0x00BFFF, fields=None, url=None):
    """
    DiscordのWebhookに送信するためのリッチなEmbedペイロードを生成する。

    :param title: Embedのタイトル
    :param description: Embedの本文
    :param color: Embedのサイドバーの色 (16進数、デフォルトは青)
    :param fields: {name: "フィールド名", value: "フィールド値", inline: True/False} のリスト
    :param url: タイトルにリンクを張るURL
    :return: Discord webhookのペイロード辞書
    """
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat() # 現在時刻をUTCで設定
    }

    if url:
        embed["url"] = url
    if fields:
        embed["fields"] = fields

    payload = {
        "embeds": [embed]
    }
    return payload

def generate_simple_text_payload(content):
    """
    シンプルなテキストメッセージのペイロードを生成する。
    :param content: 送信するテキスト内容
    :return: Discord webhookのペイロード辞書
    """
    payload = {
        "content": content
    }
    return payload

# このヘルパースクリプトは直接実行されることを想定していません。
# 他のスクリプトからインポートして利用されます。
if __name__ == '__main__':
    print("This script is a helper module and should not be run directly.")
    # Example usage (for testing purposes, if needed)
    # from datetime import datetime, timezone
    # payload = generate_discord_embed_payload(
    #     "テスト通知",
    #     "これはテストメッセージです。",
    #     color=0xFF0000,
    #     fields=[{"name": "フィールド1", "value": "値1", "inline": True}]
    # )
    # print(json.dumps(payload, ensure_ascii=False, indent=2))
