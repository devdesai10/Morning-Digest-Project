import json
import os
import time
import random
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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

# ---- Rate-limit & caching settings (free tier friendly) ----
REQUEST_DELAY_SECONDS = 0.35
MAX_RETRIES = 6
CACHE_FILE = ".sportsdb_cache.json"
TEAMID_TTL_SECONDS = 30 * 24 * 3600   # 30 days
EVENTS_TTL_SECONDS = 15 * 60          # 15 minutes

# ✅ New: Only include teams with games within this many days (today/tomorrow).
INCLUDE_WITHIN_DAYS = 1

def _safe_int(x):
    try:
        return int(x)
    except Exception:
        return None

def _base_url(api_key: str) -> str:
    # If you ever see domain issues, swap to:
    # return f"https://www.thesportsdb.com/api/v1/json/{api_key}"
    return f"https://thesportsdb.com/api/v1/json/{api_key}"

def _load_cache() -> dict:
    if not os.path.exists(CACHE_FILE):
        return {"team_ids": {}, "events": {}}
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        if "team_ids" not in data:
            data["team_ids"] = {}
        if "events" not in data:
            data["events"] = {}
        return data
    except Exception:
        return {"team_ids": {}, "events": {}}

def _save_cache(cache: dict) -> None:
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass

def _request_json(session: requests.Session, url: str, params: dict):
    time.sleep(REQUEST_DELAY_SECONDS)

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(url, params=params, timeout=25)

            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    sleep_s = int(retry_after)
                else:
                    sleep_s = min(30, int((2 ** (attempt - 1)) + random.random()))
                time.sleep(sleep_s)
                continue

            r.raise_for_status()
            return r.json()

        except requests.RequestException as e:
            last_err = e
            sleep_s = min(20, int((2 ** (attempt - 1)) + random.random()))
            time.sleep(sleep_s)

    raise last_err if last_err else RuntimeError("Request failed without exception")

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
        if len(t) == 5:  # HH:MM
            t = t + ":00"
        dt_utc = datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        local = dt_utc.astimezone(ZoneInfo(tz_name))
        return local.strftime("%I:%M %p").lstrip("0")
    except Exception:
        return ""

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

def _get_events_cached(session: requests.Session, base_url: str, cache: dict, cache_key: str, url_path: str, params: dict):
    now = int(time.time())
    cached = cache["events"].get(cache_key)
    if cached and (now - cached.get("ts", 0)) < EVENTS_TTL_SECONDS:
        return cached.get("data")

    data = _request_json(session, f"{base_url}/{url_path}", params)
    cache["events"][cache_key] = {"data": data, "ts": now}
    _save_cache(cache)
    return data

def _get_last_events(session: requests.Session, base_url: str, cache: dict, team_id: str):
    key = f"last:{team_id}"
    data = _get_events_cached(session, base_url, cache, key, "eventslast.php", {"id": team_id})
    return data.get("results") or []

def _get_next_events(session: requests.Session, base_url: str, cache: dict, team_id: str):
    key = f"next:{team_id}"
    data = _get_events_cached(session, base_url, cache, key, "eventsnext.php", {"id": team_id})
    return data.get("events") or []

def _find_next_event_within_days(next_events, today_local, max_days: int):
    """
    Returns the first upcoming event whose date is between today and (today + max_days), inclusive.
    """
    if not next_events:
        return None

    latest_allowed = today_local + timedelta(days=max_days)

    for e in next_events:
        d = _parse_event_date(e.get("dateEvent") or "")
        if not d:
            continue
        if today_local <= d <= latest_allowed:
            return e

    return None

def build_sports_digest(teams_dict: dict, tz_name: str, api_key: str, high_scoring_thresholds: dict):
    """
    Returns (yesterday_block, today_block, important_events_block)

    ✅ FILTERING RULES:
    - Skip teams NOT FOUND entirely (no line)
    - Skip teams that:
        * did NOT play yesterday, AND
        * do NOT play today or tomorrow (within INCLUDE_WITHIN_DAYS)
    - Yesterday section:
        * show final if played yesterday
        * else show next game ONLY if within 1 day
    - Today section:
        * show today’s game if today
        * else show next game ONLY if within 1 day
    """
    base_url = _base_url(api_key)
    cache = _load_cache()

    today_local = datetime.now(ZoneInfo(tz_name)).date()
    yesterday_local = today_local - timedelta(days=1)

    yesterday_lines = []
    today_lines = []
    important_lines = []

    with requests.Session() as session:
        for league, teams in teams_dict.items():
            emoji = LEAGUE_EMOJI.get(league, "🏟️")

            for t in teams:
                lookup = TEAM_OVERRIDES.get(t, t)

                # If API errors, we skip to keep the digest clean
                try:
                    team_id = _get_team_id(session, base_url, cache, lookup)
                except Exception:
                    continue

                # ✅ Skip if not found
                if not team_id:
                    continue

                try:
                    last_events = _get_last_events(session, base_url, cache, team_id)
                    next_events = _get_next_events(session, base_url, cache, team_id)
                except Exception:
                    # rate-limited or API issues → skip
                    continue

                # Check if played yesterday
                played_yesterday_event = None
                for e in last_events:
                    d = _parse_event_date(e.get("dateEvent") or "")
                    if d == yesterday_local:
                        played_yesterday_event = e
                        break

                # Check if has a game today or tomorrow
                next_soon_event = _find_next_event_within_days(next_events, today_local, INCLUDE_WITHIN_DAYS)

                # ✅ If neither condition met, remove team from digest
                if not played_yesterday_event and not next_soon_event:
                    continue

                # ----- YESTERDAY -----
                if played_yesterday_event:
                    final = _format_final(played_yesterday_event)
                    if final:
                        yesterday_lines.append(f"• {emoji} {t}: {final}")

                        hs = _safe_int(played_yesterday_event.get("intHomeScore"))
                        a_s = _safe_int(played_yesterday_event.get("intAwayScore"))
                        total = (hs or 0) + (a_s or 0)
                        thresh = _safe_int(high_scoring_thresholds.get(league))
                        if thresh and total >= thresh:
                            important_lines.append(f"🔥 {emoji} High scoring ({league}): {final} (Total {total})")
                else:
                    # Only show "Next" if within 1 day (we already ensured next_soon_event exists)
                    yesterday_lines.append(f"• {emoji} {t}: Next — {_format_upcoming(next_soon_event, tz_name)}")

                # ----- TODAY -----
                today_event = None
                for e in next_events:
                    d = _parse_event_date(e.get("dateEvent") or "")
                    if d == today_local:
                        today_event = e
                        break

                if today_event:
                    today_lines.append(f"• {emoji} {t}: {_format_upcoming(today_event, tz_name)}")
                else:
                    # If no game today, but they’re still within the window, show next soon (today/tomorrow)
                    if next_soon_event:
                        today_lines.append(f"• {emoji} {t}: Next — {_format_upcoming(next_soon_event, tz_name)}")

    if not yesterday_lines:
        yesterday_lines.append("• (No teams played yesterday, and no games today/tomorrow.)")
    if not today_lines:
        today_lines.append("• (No games today, and no games tomorrow.)")
    if not important_lines:
        important_lines.append("• (No high-scoring games detected from yesterday.)")

    return (
        "\n".join(yesterday_lines),
        "\n".join(today_lines),
        "\n".join(important_lines)
    )
