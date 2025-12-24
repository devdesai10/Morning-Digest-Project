import json
from datetime import datetime
from pathlib import Path

from notify_discord import send_discord_webhook
from sports import build_digest_blocks  # or whatever your current function is

def main():
    base_dir = Path(__file__).resolve().parent
    config_path = base_dir / "config.json"

    with open(config_path, "r") as f:
        config = json.load(f)

    teams = config["teams"]
    webhook_url = config["discord"]["webhook_url"]

    settings = config.get("settings", {})
    tz_name = settings.get("timezone", "America/New_York")
    api_key = settings.get("sportsdb_api_key", "123")
    top_n = settings.get("top_games_count", 3)

    favorites_block, top_games_block = build_digest_blocks(
        teams_dict=teams,
        tz_name=tz_name,
        api_key=api_key,
        top_games_count=top_n
    )

    stamp = datetime.now().strftime("%a %b %d")
    body = (
        f"🏟️ Sports Digest — {stamp}\n\n"
        f"⭐️ **Favorite Teams**\n{favorites_block}\n\n"
        f"**Top Games**\n{top_games_block}"
    )

    send_discord_webhook(webhook_url, body)
    print("✅ Posted sports digest to Discord!")

if __name__ == "__main__":
    main()
