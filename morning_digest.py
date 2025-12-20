import os
import requests
from datetime import datetime
from twilio.rest import Client

NEWS_API_KEY = os.environ["NEWS_API_KEY"]
OPENWEATHER_API_KEY = os.environ["OPENWEATHER_API_KEY"]
SPORTSDB_API_KEY = os.environ.get("SPORTSDB_API_KEY", "1")  # TheSportsDB demo key often used
TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_FROM = os.environ["TWILIO_FROM"]     # e.g. "+1XXXXXXXXXX"
TWILIO_TO = os.environ["TWILIO_TO"]         # your phone "+1XXXXXXXXXX"

# Your location (simple: lat/lon). Example: NYC-ish
LAT = float(os.environ.get("LAT", "40.7128"))
LON = float(os.environ.get("LON", "-74.0060"))

# Sports: TheSportsDB team id (you can swap this later per your team/league)
TEAM_ID = os.environ.get("SPORTS_TEAM_ID", "133602")

def get_weather():
    # OpenWeather One Call 3.0 "onecall" style endpoint
    # Docs: https://openweathermap.org/api/one-call-3
    url = "https://api.openweathermap.org/data/3.0/onecall"
    params = {
        "lat": LAT,
        "lon": LON,
        "appid": OPENWEATHER_API_KEY,
        "units": "imperial",
        "exclude": "minutely,hourly,alerts"
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    today = data["daily"][0]
    desc = today["weather"][0]["description"].title()
    high = round(today["temp"]["max"])
    low = round(today["temp"]["min"])
    pop = round(today.get("pop", 0) * 100)  # precipitation probability

    return f"Weather: {desc}, H {high}° / L {low}°, Rain {pop}%"

def get_news():
    # NewsAPI top headlines
    # Docs: https://newsapi.org/docs/endpoints/top-headlines
    url = "https://newsapi.org/v2/top-headlines"
    params = {
        "apiKey": NEWS_API_KEY,
        "country": "us",
        "pageSize": 3
        # Optional: "category": "business"
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    articles = r.json().get("articles", [])

    if not articles:
        return ["News: (No headlines returned)"]

    lines = []
    for a in articles:
        title = (a.get("title") or "").strip()
        source = (a.get("source", {}).get("name") or "").strip()
        if title:
            lines.append(f"- {title} ({source})")
    return lines[:3] if lines else ["News: (No usable headlines)"]

def get_sports():
    # TheSportsDB upcoming events for a team
    # Often: https://www.thesportsdb.com/api/v1/json/{APIKEY}/eventsnext.php?id={TEAM_ID}
    url = f"https://www.thesportsdb.com/api/v1/json/{SPORTSDB_API_KEY}/eventsnext.php"
    params = {"id": TEAM_ID}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    events = data.get("events") or []

    if not events:
        return "Sports: No upcoming events found."

    e = events[0]
    home = e.get("strHomeTeam", "Home")
    away = e.get("strAwayTeam", "Away")
    date = e.get("dateEvent", "")
    time = e.get("strTime", "")  # may be empty depending on league/data
    return f"Sports: Next game {away} @ {home} on {date} {time}".strip()

def build_message():
    stamp = datetime.now().strftime("%a %b %d")
    weather_line = get_weather()
    sports_line = get_sports()
    news_lines = get_news()

    msg = [
        f"Morning Digest ({stamp})",
        weather_line,
        sports_line,
        "Top News:",
        *news_lines
    ]
    # Keep it SMS-friendly
    return "\n".join(msg)[:1500]

def send_sms(body: str):
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    client.messages.create(
        body=body,
        from_=TWILIO_FROM,
        to=TWILIO_TO
    )

if __name__ == "__main__":
    text = build_message()
    send_sms(text)
    print("Sent.")
