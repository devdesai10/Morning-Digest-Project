import json
import os
import time
import random
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_SCRIPT_DIR = Path(__file__).resolve().parent

# --- Team abbreviations ---
TEAM_ABBREVS = {
    # NBA
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA", "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP", "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR", "Utah Jazz": "UTA", "Washington Wizards": "WAS",
    # NFL
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN",
    "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
    # MLB
    "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL", "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS", "Chicago Cubs": "CHC", "Chicago White Sox": "CWS",
    "Cincinnati Reds": "CIN", "Cleveland Guardians": "CLE", "Colorado Rockies": "COL",
    "Detroit Tigers": "DET", "Houston Astros": "HOU", "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA", "Los Angeles Dodgers": "LAD", "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL", "Minnesota Twins": "MIN", "New York Mets": "NYM",
    "New York Yankees": "NYY", "Oakland Athletics": "OAK", "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT", "San Diego Padres": "SD", "San Francisco Giants": "SF",
    "Seattle Mariners": "SEA", "St. Louis Cardinals": "STL", "Tampa Bay Rays": "TB",
    "Texas Rangers": "TEX", "Toronto Blue Jays": "TOR", "Washington Nationals": "WSH",
    # Premier League
    "Arsenal": "ARS", "Aston Villa": "AVL", "Bournemouth": "BOU", "Brentford": "BRE",
    "Brighton & Hove Albion": "BHA", "Brighton": "BHA", "Chelsea": "CHE",
    "Crystal Palace": "CRY", "Everton": "EVE", "Fulham": "FUL", "Ipswich Town": "IPS",
    "Leicester City": "LEI", "Liverpool": "LIV", "Manchester City": "MCI",
    "Manchester United": "MUN", "Newcastle United": "NEW", "Nottingham Forest": "NFO",
    "Southampton": "SOU", "Tottenham Hotspur": "TOT", "West Ham United": "WHU",
    "Wolverhampton Wanderers": "WOL", "Wolverhampton": "WOL", "Sunderland":"SUN",
}

def _abbrev(team: str) -> str:
    """Return abbreviation if known, otherwise return the original name."""
    return TEAM_ABBREVS.get(team, team)

# --- League config ---
# Each entry: display name -> (TheSportsDB league ID, API league name for eventsday.php)
LEAGUES = {
    "🏀 NBA":              (4387, "NBA"),
    "🏈 NFL":              (4391, "NFL"),
    "⚾ MLB":              (4424, "MLB"),
    "⚽ Premier League":   (4328, "English Premier League"),
    "🏎️ F1":               (4370, "Formula 1"),
    "🥊 UFC":              (4443, "UFC"),
    "⚽ World Cup":        (4429, "FIFA World Cup"),
    "⚾ WBC":              (5755, "World Baseball Classic"),
    "🏀 FIBA World Cup":   (4549, "FIBA World Cup"),
}

# --- Request / cache settings ---
REQUEST_DELAY_SECONDS = 0.15
MAX_RETRIES = 2
MAX_429_SLEEP_SECONDS = 2
CACHE_FILE = str(_SCRIPT_DIR / ".sportsdb_cache.json")
EVENTS_TTL_SECONDS = 60 * 60  # 1 hour

def _base_url(api_key: str) -> str:
    return f"https://thesportsdb.com/api/v1/json/{api_key}"

# --- Cache helpers ---

def _load_cache() -> dict:
    if not os.path.exists(CACHE_FILE):
        return {"events": {}}
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        data.setdefault("events", {})
        return data
    except Exception:
        return {"events": {}}

def _save_cache(cache: dict) -> None:
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass

def _cache_get(cache: dict, key: str, ttl_seconds: int):
    now = int(time.time())
    item = cache["events"].get(key)
    if item and (now - item.get("ts", 0)) < ttl_seconds:
        return item.get("data")
    return None

def _cache_set(cache: dict, key: str, data):
    cache["events"][key] = {"data": data, "ts": int(time.time())}
    _save_cache(cache)

# --- HTTP helpers ---

class RateLimited(Exception):
    pass

def _request_json(session: requests.Session, url: str, params: dict):
    time.sleep(REQUEST_DELAY_SECONDS)
    for attempt in range(1, MAX_RETRIES + 1):
        r = session.get(url, params=params, timeout=15)
        if r.status_code == 429:
            time.sleep(min(MAX_429_SLEEP_SECONDS, 0.5 + random.random()))
            if attempt == MAX_RETRIES:
                raise RateLimited(f"429 rate-limited: {r.url}")
            continue
        r.raise_for_status()
        return r.json()
    raise RateLimited("Rate limited")

# --- Parsing / formatting helpers ---

def _parse_event_date(date_str: str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None

def _safe_int(x):
    try:
        return int(x)
    except Exception:
        return None

def _has_final_score(event) -> bool:
    return (_safe_int(event.get("intHomeScore")) is not None
            and _safe_int(event.get("intAwayScore")) is not None)

def _format_time_local(date_str: str, time_str: str, tz_name: str) -> str:
    if not date_str or not time_str:
        return ""
    t = time_str.strip()
    if t in ("", "00:00:00", "00:00"):
        return ""
    try:
        if len(t) == 5:
            t += ":00"
        dt_utc = datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        local = dt_utc.astimezone(ZoneInfo(tz_name))
        return local.strftime("%-I:%M%p").upper()
    except Exception:
        return ""

def _format_event_line(event, tz_name: str) -> str:
    """Format a single event into a display line using team abbreviations."""
    home = event.get("strHomeTeam", "?")
    away = event.get("strAwayTeam", "?")
    event_name = event.get("strEvent", "")
    date_str = event.get("dateEvent") or ""
    time_str = event.get("strTime") or ""

    # For non-team sports (F1, UFC, etc.) — use event name directly
    if home == away or not away or home == "?":
        time_local = _format_time_local(date_str, time_str, tz_name)
        if _has_final_score(event):
            return f"  {event_name} (Final)"
        elif time_local:
            return f"  {event_name} ({time_local})"
        return f"  {event_name}"

    h = _abbrev(home)
    a = _abbrev(away)

    # Team vs team
    if _has_final_score(event):
        hs = _safe_int(event.get("intHomeScore"))
        a_s = _safe_int(event.get("intAwayScore"))
        return f"  {a} {a_s} @ {h} {hs} ✓"

    time_local = _format_time_local(date_str, time_str, tz_name)
    if time_local:
        return f"  {a} @ {h} ({time_local})"
    return f"  {a} @ {h}"

# --- League event fetching ---

def _get_league_events_today(session, base_url, cache, league_id, league_api_name, today_local):
    """
    Fetch today's events for a league.
    eventsday.php (by league name) is the most complete source on the free API tier.
    past/next endpoints are used as fallbacks to catch API lag edge cases.
    """
    today_str = today_local.strftime("%Y-%m-%d")
    today_events = []
    seen_ids = set()

    def _add_events(events_list):
        for e in (events_list or []):
            if _parse_event_date(e.get("dateEvent") or "") == today_local:
                eid = e.get("idEvent")
                if eid not in seen_ids:
                    seen_ids.add(eid)
                    today_events.append(e)

    # Primary: eventsday returns all events for a specific date by league name
    day_key = f"eventsday:{league_id}:{today_str}"
    day_data = _cache_get(cache, day_key, EVENTS_TTL_SECONDS)
    if day_data is None:
        try:
            day_data = _request_json(session, f"{base_url}/eventsday.php", {"d": today_str, "l": league_api_name})
            _cache_set(cache, day_key, day_data)
        except (RateLimited, Exception):
            day_data = {}
    _add_events(day_data.get("events"))

    # Fallback: past events (catches finished games the day endpoint may miss)
    past_key = f"pastleague:{league_id}"
    past_data = _cache_get(cache, past_key, EVENTS_TTL_SECONDS)
    if past_data is None:
        try:
            past_data = _request_json(session, f"{base_url}/eventspastleague.php", {"id": league_id})
            _cache_set(cache, past_key, past_data)
        except (RateLimited, Exception):
            past_data = {}
    _add_events(past_data.get("events"))

    # Fallback: next events (catches upcoming games not yet on eventsday)
    next_key = f"nextleague:{league_id}"
    next_data = _cache_get(cache, next_key, EVENTS_TTL_SECONDS)
    if next_data is None:
        try:
            next_data = _request_json(session, f"{base_url}/eventsnextleague.php", {"id": league_id})
            _cache_set(cache, next_key, next_data)
        except (RateLimited, Exception):
            next_data = {}
    _add_events(next_data.get("events"))

    return today_events


# --- Main entry point ---

def build_todays_games(tz_name: str, api_key: str) -> str:
    """
    Build the sports digest showing only today's active games/events.
    Leagues with no games today are omitted entirely.
    """
    base_url = _base_url(api_key)
    cache = _load_cache()
    today_local = datetime.now(ZoneInfo(tz_name)).date()

    sections = []

    with requests.Session() as session:
        for league_name, (league_id, league_api_name) in LEAGUES.items():
            try:
                events = _get_league_events_today(session, base_url, cache, league_id, league_api_name, today_local)
            except Exception:
                continue

            if not events:
                continue

            lines = [f"**{league_name}**"]
            for e in events:
                lines.append(_format_event_line(e, tz_name))

            sections.append("\n".join(lines))

    if not sections:
        return "No games or events today."

    return "\n\n".join(sections)
