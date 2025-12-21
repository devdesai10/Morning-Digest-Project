import requests

DISCORD_MAX = 2000

def _split_message(text: str, limit: int = DISCORD_MAX):
    text = (text or "").strip()
    if len(text) <= limit:
        return [text]

    parts = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        parts.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts

def send_discord_webhook(webhook_url: str, body: str):
    for chunk in _split_message(body):
        r = requests.post(webhook_url, json={"content": chunk}, timeout=20)
        r.raise_for_status()
