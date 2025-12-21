import requests

DISCORD_MAX = 2000  # Discord message character limit

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
    if not webhook_url or "discord.com/api/webhooks" not in webhook_url:
        raise ValueError("Webhook URL looks invalid. Your a dumb motherfucker")

    for chunk in _split_message(body):
        r = requests.post(webhook_url, json={"content": chunk}, timeout=20)
        r.raise_for_status()
