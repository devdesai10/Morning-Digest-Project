import json
import os
from datetime import datetime

from notify_discord import send_discord_webhook
from weather import get_weather_multi
from sports import build_sports_blocks
from news import get_important_sports_news

OPENWEATHER_API_KEY = os.environ["OPENWEATHER_API_KEY"]
NEWS_API_KEY = os.environ["NEWS_API_KEY"]

def main():
    with open("config.json") as f:
        config = json.load(f)

    # Weather (multi-location)
    weather_text = get_weather_multi(config["locations"], OPENWEATHER_API_KEY)

    # Sports (Yesterday / Today / Important events)
    yest, today, highlights = build_sports_blocks(config["teams"])

    # News-based important events (trades/injuries/all-star/etc.)
    news_highlights = get_important_sports_news(NEWS_API_KEY, config["teams"])

    stamp = datetime.now().strftime("%a %b %d")

    body = (
        f"🌤️ Morning Digest — {stamp}\n\n"
        f"**Weather**\n{weather_text}\n\n"
        f"**Yesterday**\n{yest}\n\n"
        f"**Today**\n{today}\n\n"
        f"**Important Events**\n{highlights}\n{news_highlights}"
    )

    send_discord_webhook(config["discord"]["webhook_url"], body)
    print("✅ Posted to Discord!")

if __name__ == "__main__":
    main()
