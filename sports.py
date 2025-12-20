import requests
from datetime import datetime, timedelta

SPORTSDB_API_KEY = "1"  # public demo key
BASE_URL = "https://www.thesportsdb.com/api/v1/json"

def get_event_text(event):
    home = event.get("strHomeTeam", "?")
    away = event.get("strAwayTeam", "?")
    date = event.get("dateEvent")
    time = event.get("strTimeLocal", event.get("strTime", ""))
    score_h = event.get("intHomeScore")
    score_a = event.get("intAwayScore")
    if score_h and score_a:
        return f"{away} {score_a} - {home} {score_h} ({date})"
    return f"{away} vs {home} ({date} {time})"

def get_team_events(team_name):
    try:
        search = requests.get(f"{BASE_URL}/{SPORTSDB_API_KEY}/searchteams.php", params={"t": team_name}).json()
        team = search["teams"][0]
        team_id = team["idTeam"]
    except Exception:
        return None, None

    prev = requests.get(f"{BASE_URL}/{SPORTSDB_API_KEY}/eventslast.php", params={"id": team_id}).json().get("results", [])
    nexts = requests.get(f"{BASE_URL}/{SPORTSDB_API_KEY}/eventsnext.php", params={"id": team_id}).json().get("events", [])
    return prev, nexts

def get_sports_summary(teams_dict):
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)

    lines = []

    for league, teams in teams_dict.items():
        lines.append(f"\n🏆 {league}:")
        for t in teams:
            prev, nexts = get_team_events(t)
            if not prev and not nexts:
                lines.append(f"- {t}: (no data)")
                continue

            played_yesterday = False
            latest = None
            for e in (prev or []):
                if e["dateEvent"]:
                    event_date = datetime.strptime(e["dateEvent"], "%Y-%m-%d").date()
                    if event_date == yesterday:
                        lines.append(f"- {get_event_text(e)}")
                        played_yesterday = True
                        break
                    latest = e

            if not played_yesterday:
                if nexts:
                    lines.append(f"- Next: {get_event_text(nexts[0])}")
                elif latest:
                    lines.append(f"- Last: {get_event_text(latest)}")

    return "\n".join(lines)
