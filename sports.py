import json
import os
import time
import random
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_SCRIPT_DIR = Path(__file__).resolve().parent

TEAM_OVERRIDES = {
    "Knicks": "New York Knicks",
    "76ers": "Philadelphia 76ers",
    "Nets": "Brooklyn Nets",
    "Giants": "New York Giants",
    "Jets": "New York Jets",
    "Eagles": "Philadelphia Eagles",
    "Yankees": "New York Yankees",
    "Nationals": "Washington Nationals",
    "Rutgers": "Rutgers Scarlet Knights"
}

LEAGUE_EMOJI = {
    "NBA": "🏀",
    "NFL": "🏈",
    "MLB": "⚾",
    "College": "🎓"
}

LEAGUE_IDS = {
    "NBA": 4387,
    "NFL": 4391,
    "MLB": 4424
}

# --- FAST MODE SETTINGS ---
REQUEST_DELAY_SECONDS = 0.15
MAX_RETRIES = 2                 # ✅ hard cap
MAX_429_SLEEP_SECONDS = 2       # ✅ never wait long
CACHE_FILE = str(_SCRIPT_DIR / ".sportsdb_cache.json")
TEAMID_TTL_SECONDS = 30 * 24 * 3600
EVENTS_TTL_SECONDS = 60 * 60    # ✅ 1 hour cache

INCLUDE_WITHIN_DAYS = 1         # today/tomorrow

def _base_url(api_key: str) -> str:
    return f"https://thesportsdb.com/api/v1/json/{api_key}"

def _safe_int(x):
    try:
        return int(x)
    except Exception:
        return None

def _load_cache() -> dict:
    if not os.path.exists(CACHE_FILE):
        return {"team_ids": {}, "events": {}}
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        data.setdefault("team_ids", {})
        data.setdefault("events", {})
        return data
    except Exception:
        return {"team_ids": {}, "events": {}}

def _save_cache(cache: dict) -> None:
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass

class RateLimited(Exception):
    pass

def _request_json(session: requests.Session, url: str, params: dict):
    time.sleep(REQUEST_DELAY_SECONDS)

    for attempt in range(1, MAX_RETRIES + 1):
        r = session.get(url, params=params, timeout=15)

        if r.status_code == 429:
            # ✅ don’t wait forever — short sleep then give up
            time.sleep(min(MAX_429_SLEEP_SECONDS, 0.5 + random.random()))
            if attempt == MAX_RETRIES:
                raise RateLimited(f"429 rate-limited: {r.url}")
            continue

        r.raise_for_status()
        return r.json()

    raise RateLimited("Rate limited")

def _cache_get(cache: dict, key: str, ttl_seconds: int):
    now = int(time.time())
    item = cache["events"].get(key)
    if item and (now - item.get("ts", 0)) < ttl_seconds:
        return item.get("data")
    return None

def _cache_set(cache: dict, key: str, data):
    cache["events"][key] = {"data": data, "ts": int(time.time())}
    _save_cache(cache)

def _parse_event_date(date_str: str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None

def _format_time_local(date_str: str, time_str: str, tz_name: str):
    if not date_str or not time_str:
        return ""
    t = time_str.strip()
    if t in ("", "00:00:00", "00:00"):
        return ""
    try:
        if len(t) == 5:
            t = t + ":00"
        dt_utc = datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        local = dt_utc.astimezone(ZoneInfo(tz_name))
        return local.strftime("%I:%M %p").lstrip("0")
    except Exception:
        return ""

def _has_final_score(event) -> bool:
    """True only if both home and away scores are present (game is actually finished)."""
    return _safe_int(event.get("intHomeScore")) is not None and _safe_int(event.get("intAwayScore")) is not None

def _format_final(event):
    home = event.get("strHomeTeam", "?")
    away = event.get("strAwayTeam", "?")
    hs = _safe_int(event.get("intHomeScore"))
    a_s = _safe_int(event.get("intAwayScore"))
    date = event.get("dateEvent") or ""
    if hs is None or a_s is None:
        return None
    return f"{away} {a_s} @ {home} {hs} ({date})"

def _format_upcoming(event, tz_name: str):
    home = event.get("strHomeTeam", "?")
    away = event.get("strAwayTeam", "?")
    date = event.get("dateEvent") or ""
    time_raw = event.get("strTime") or ""
    t_local = _format_time_local(date, time_raw, tz_name)
    if t_local:
        return f"{away} vs {home} — {t_local} ({date})"
    return f"{away} vs {home} — ({date})"

def _get_team_id(session: requests.Session, base_url: str, cache: dict, team_name: str):
    key = team_name.lower().strip()
    now = int(time.time())

    cached = cache["team_ids"].get(key)
    if cached and (now - cached.get("ts", 0)) < TEAMID_TTL_SECONDS:
        return cached.get("id")

    data = _request_json(session, f"{base_url}/searchteams.php", {"t": team_name})
    teams = data.get("teams") or []
    if not teams:
        return None

    team_id = teams[0].get("idTeam")
    cache["team_ids"][key] = {"id": team_id, "ts": now}
    _save_cache(cache)
    return team_id

def _get_team_last_next(session: requests.Session, base_url: str, cache: dict, team_id: str):
    # cache both calls for 1 hour
    last_key = f"last:{team_id}"
    next_key = f"next:{team_id}"

    last_data = _cache_get(cache, last_key, EVENTS_TTL_SECONDS)
    next_data = _cache_get(cache, next_key, EVENTS_TTL_SECONDS)

    if last_data is None:
        last_data = _request_json(session, f"{base_url}/eventslast.php", {"id": team_id})
        _cache_set(cache, last_key, last_data)

    if next_data is None:
        next_data = _request_json(session, f"{base_url}/eventsnext.php", {"id": team_id})
        _cache_set(cache, next_key, next_data)

    return (last_data.get("results") or []), (next_data.get("events") or [])

def _find_next_event_within_days(next_events, today_local, max_days: int):
    latest_allowed = today_local + timedelta(days=max_days)
    for e in next_events or []:
        d = _parse_event_date(e.get("dateEvent") or "")
        if d and today_local <= d <= latest_allowed:
            return e
    return None

def _score_total(event):
    hs = _safe_int(event.get("intHomeScore"))
    a_s = _safe_int(event.get("intAwayScore"))
    if hs is None or a_s is None:
        return None
    return hs + a_s

def _get_past_league_events(session: requests.Session, base_url: str, cache: dict, league_id: int):
    key = f"pastleague:{league_id}"
    cached = _cache_get(cache, key, EVENTS_TTL_SECONDS)
    if cached is not None:
        return cached.get("events") or []

    data = _request_json(session, f"{base_url}/eventspastleague.php", {"id": league_id})
    _cache_set(cache, key, data)
    return data.get("events") or []

def build_todays_games(teams_dict: dict, tz_name: str, api_key: str) -> str:
    """Return a single block of today's games for all configured teams."""
    base_url = _base_url(api_key)
    cache = _load_cache()
    today_local = datetime.now(ZoneInfo(tz_name)).date()

    lines = []

    with requests.Session() as session:
        for league, teams in teams_dict.items():
            emoji = LEAGUE_EMOJI.get(league, "🏟️")

            for t in teams:
                lookup = TEAM_OVERRIDES.get(t, t)
                try:
                    team_id = _get_team_id(session, base_url, cache, lookup)
                    if not team_id:
                        continue

                    last_events, next_events = _get_team_last_next(session, base_url, cache, team_id)

                    # Check last_events — API lag can put today's game here
                    today_event = None
                    for e in last_events:
                        if _parse_event_date(e.get("dateEvent") or "") == today_local:
                            today_event = e
                            break

                    # Check next_events for today
                    if not today_event:
                        for e in next_events or []:
                            if _parse_event_date(e.get("dateEvent") or "") == today_local:
                                today_event = e
                                break

                    if not today_event:
                        continue

                    # If it has scores already, show as final; otherwise show as upcoming
                    if _has_final_score(today_event):
                        final = _format_final(today_event)
                        if final:
                            lines.append(f"• {emoji} {t}: {final}")
                    else:
                        lines.append(f"• {emoji} {t}: {_format_upcoming(today_event, tz_name)}")

                except RateLimited:
                    continue
                except Exception:
                    continue

    if not lines:
        return "• No games today for your teams."

    return "\n".join(lines)
