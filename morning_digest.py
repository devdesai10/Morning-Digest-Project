import os
from datetime import datetime
from twilio.rest import Client
from sports import get_sports_summary
from news import get_sports_news
from weather import get_weather
import json

NEWS_API_KEY = os.environ["NEWS_API_KEY"]
OPENWEATHER_API_KEY = os.environ["OPENWEATHER_API_KEY"]
TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]

def send_sms(body, from_, to):
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    client.messages.create(body=body, from_=from_, to=to)

def main():
    with open("config.json") as f:
        config = json.load(f)

    lat = config["location"]["lat"]
    lon = config["location"]["lon"]

    weather = get_weather(lat, lon, OPENWEATHER_API_KEY)
    sports_summary = get_sports_summary(config["teams"])
    sports_news = get_sports_news(NEWS_API_KEY)

    today = datetime.now().strftime("%a %b %d")

    body = (
        f"Morning Sports Digest ({today}) 🗞️\n\n"
        f"{weather}\n\n"
        f"{sports_summary}\n\n"
        f"Top Sports News:\n{sports_news}"
    )

    send_sms(body, config["twilio"]["from"], config["twilio"]["to"])
    print("✅ Sent daily digest!")

if __name__ == "__main__":
    main()
