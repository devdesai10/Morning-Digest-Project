import json
from datetime import datetime
from pathlib import Path

from notify_discord import send_discord_webhook
from sports import build_todays_games

def main():
    base_dir = Path(__file__).resolve().parent
    config_path = base_dir / "config.json"

    with open(config_path, "r") as f:
        config = json.load(f)

    webhook_url = config["discord"]["webhook_url"]
    settings = config.get("settings", {})
    tz_name = settings.get("timezone", "America/New_York")
    api_key = settings.get("sportsdb_api_key", "123")

    todays_games = build_todays_games(tz_name=tz_name, api_key=api_key)

    stamp = datetime.now().strftime("%a %b %d")
    body = f"🏟️ Sports Digest - {stamp}\n\n{todays_games}"

    send_discord_webhook(webhook_url, body)
    print("✅ Posted sports digest to Discord!")

if __name__ == "__main__":
    main()
