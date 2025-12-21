## Main File for the project

import json
from datetime import datetime
from notify_discord import send_discord_webhook
from sports import build_sports_digest

def main():
    with open("config.json", "r") as f:
        config = json.load(f)

    teams = config["teams"]
    webhook_url = config["discord"]["webhook_url"]
    tz_name = config.get("settings", {}).get("timezone", "America/New_York")
    thresholds = config.get("settings", {}).get("high_scoring_thresholds", {})

    yest, today, important = build_sports_digest(teams, tz_name, thresholds)

    stamp = datetime.now().strftime("%a %b %d")
    body = (
        f"🏟️ Sports Digest — {stamp}\n\n"
        f"**Yesterday**\n{yest}\n\n"
        f"**Today**\n{today}\n\n"
        f"**Important Events**\n{important}"
    )

    send_discord_webhook(webhook_url, body)
    print("✅ Posted sports digest to Discord!")

if __name__ == "__main__":
    main()
