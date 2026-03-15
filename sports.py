import json
import os
import time
import random
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_SCRIPT_DIR = Path(__file__).resolve().parent

# --- League config ---
# Each entry: display name -> TheSportsDB league ID
LEAGUES = {
    "NBA":                  4387,
    "NFL":                  4391,
    "MLB":                  4424,
    "Premier League":       4328,
    "F1":                   4370,
    "UFC":                  4443,
    "World Cup":            4429,
    "WBC":                  5755,
    "FIBA World Cup":       4549,
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
    """Format a single event into a display line."""
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

    # Team vs team
    if _has_final_score(event):
        hs = _safe_int(event.get("intHomeScore"))
        a_s = _safe_int(event.get("intAwayScore"))
        return f"  {away} {a_s} @ {home} {hs} (Final)"

    time_local = _format_time_local(date_str, time_str, tz_name)
    if time_local:
        return f"  {away} @ {home} ({time_local})"
    return f"  {away} @ {home}"

# --- League event fetching ---

def _get_league_events_today(session, base_url, cache, league_id, today_local):
    """
    Fetch today's events for a league by checking both past and next endpoints.
    The free API returns limited results, so we check both to handle API lag.
    """
    today_events = []

    # Check past events (API lag may put today's finished games here)
    past_key = f"pastleague:{league_id}"
    past_data = _cache_get(cache, past_key, EVENTS_TTL_SECONDS)
    if past_data is None:
        try:
            past_data = _request_json(session, f"{base_url}/eventspastleague.php", {"id": league_id})
            _cache_set(cache, past_key, past_data)
        except (RateLimited, Exception):
            past_data = {}

    for e in (past_data.get("events") or []):
        if _parse_event_date(e.get("dateEvent") or "") == today_local:
            today_events.append(e)

    # Check next events (today's upcoming games)
    next_key = f"nextleague:{league_id}"
    next_data = _cache_get(cache, next_key, EVENTS_TTL_SECONDS)
    if next_data is None:
        try:
            next_data = _request_json(session, f"{base_url}/eventsnextleague.php", {"id": league_id})
            _cache_set(cache, next_key, next_data)
        except (RateLimited, Exception):
            next_data = {}

    # Avoid duplicates by event ID
    seen_ids = {e.get("idEvent") for e in today_events}
    for e in (next_data.get("events") or []):
        if _parse_event_date(e.get("dateEvent") or "") == today_local:
            if e.get("idEvent") not in seen_ids:
                today_events.append(e)

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
        for league_name, league_id in LEAGUES.items():
            try:
                events = _get_league_events_today(session, base_url, cache, league_id, today_local)
            except Exception:
                continue

            if not events:
                continue

            lines = [f"{league_name} -"]
            for e in events:
                lines.append(_format_event_line(e, tz_name))

            sections.append("\n".join(lines))

    if not sections:
        return "No games or events today."

    return "\n\n".join(sections)
