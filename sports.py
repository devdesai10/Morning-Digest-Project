import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SPORTSDB_API_KEY = "123"  # Free demo key
BASE_URL = f"https://thesportsdb.com/api/v1/json/{SPORTSDB_API_KEY}"

# These overrides help the team search succeed more often
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

def _safe_int(x):
    try:
        return int(x)
    except Exception:
        return None

def _get_team_id(team_name: str):
    r = requests.get(f"{BASE_URL}/searchteams.php", params={"t": team_name}, timeout=20)
    r.raise_for_status()
    data = r.json()
    teams = data.get("teams") or []
    if not teams:
        return None
    return teams[0].get("idTeam")

def _get_last_events(team_id: str):
    r = requests.get(f"{BASE_URL}/eventslast.php", params={"id": team_id}, timeout=20)
    r.raise_for_status()
    return r.json().get("results") or []

def _get_next_events(team_id: str):
    r = requests.get(f"{BASE_URL}/eventsnext.php", params={"id": team_id}, timeout=20)
    r.raise_for_status()
    return r.json().get("events") or []

def _parse_event_date(date_str: str):
    # dateEvent is typically YYYY-MM-DD
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None

def _format_time_et(date_str: str, time_str: str, tz_name: str):
    """
    TheSportsDB often returns strTime in UTC (HH:MM:SS).
    Convert to your timezone and format like "7:30 PM ET".
    If missing/invalid, return "".
    """
    if not date_str or not time_str:
        return ""

    # Some APIs provide "00:00:00" when time unknown
    if time_str.strip() in ("", "00:00:00", "00:00"):
        return ""

    # Build a UTC datetime then convert
    try:
        # Normalize time
        t = time_str.strip()
        if len(t) == 5:  # HH:MM
            t = t + ":00"
        dt_utc = datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        local = dt_utc.astimezone(ZoneInfo(tz_name))
        return local.strftime("%-I:%M %p").replace("AM", "AM").replace("PM", "PM")
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
    # Format required: Away @ Home with scores
    return f"{away} {a_s} @ {home} {hs} ({date})"

def _format_upcoming(event, tz_name: str):
    home = event.get("strHomeTeam", "?")
    away = event.get("strAwayTeam", "?")
    date = event.get("dateEvent") or ""
    time_raw = event.get("strTime") or ""   # often UTC
    time_local = _format_time_et(date, time_raw, tz_name)

    # Required format: Away vs Home
    if time_local:
        return f"{away} vs {home} — {time_local} ({date})"
    return f"{away} vs {home} — ({date})"

def build_sports_digest(teams_dict: dict, tz_name: str, high_scoring_thresholds: dict):
    """
    Returns (yesterday_block, today_block, important_events_block)
    - Yesterday: final if played yesterday; else next scheduled game
    - Today: today's game if exists; else next scheduled
    - Important events: auto high-scoring games from yesterday
    """
    now_local = datetime.now(ZoneInfo(tz_name)).date()
    yesterday_local = now_local - timedelta(days=1)

    yesterday_lines = []
    today_lines = []
    important_lines = []

    for league, teams in teams_dict.items():
        for t in teams:
            lookup = TEAM_OVERRIDES.get(t, t)
            team_id = _get_team_id(lookup)

            if not team_id:
                yesterday_lines.append(f"• {t}: (team not found)")
                today_lines.append(f"• {t}: (team not found)")
                continue

            last_events = _get_last_events(team_id)
            next_events = _get_next_events(team_id)

            # ---- YESTERDAY ----
            found_yesterday = False
            for e in last_events:
                d = _parse_event_date(e.get("dateEvent") or "")
                if not d:
                    continue

                if d == yesterday_local:
                    final = _format_final(e)
                    if final:
                        yesterday_lines.append(f"• {t}: {final}")
                        found_yesterday = True

                        hs = _safe_int(e.get("intHomeScore"))
                        a_s = _safe_int(e.get("intAwayScore"))
                        total = (hs or 0) + (a_s or 0)
                        thresh = _safe_int(high_scoring_thresholds.get(league))
                        if thresh and total >= thresh:
                            important_lines.append(f"🔥 High scoring ({league}): {final} (Total {total})")
                    break

            if not found_yesterday:
                if next_events:
                    yesterday_lines.append(f"• {t}: Next — {_format_upcoming(next_events[0], tz_name)}")
                else:
                    yesterday_lines.append(f"• {t}: No recent/next game found")

            # ---- TODAY ----
            found_today = False
            for e in next_events:
                d = _parse_event_date(e.get("dateEvent") or "")
                if not d:
                    continue

                if d == now_local:
                    today_lines.append(f"• {t}: {_format_upcoming(e, tz_name)}")
                    found_today = True
                    break

            if not found_today:
                if next_events:
                    today_lines.append(f"• {t}: Next — {_format_upcoming(next_events[0], tz_name)}")
                else:
                    today_lines.append(f"• {t}: No game today / no upcoming found")

    if not important_lines:
        important_lines.append("• (No high-scoring games detected from yesterday.)")

    return (
        "\n".join(yesterday_lines) if yesterday_lines else "• (None)",
        "\n".join(today_lines) if today_lines else "• (None)",
        "\n".join(important_lines)
        "Made By Devan, also fuck you chris"
    )
