import requests
from datetime import datetime, timedelta

SPORTSDB_API_KEY = "1"  # TheSportsDB demo key
BASE_URL = f"https://www.thesportsdb.com/api/v1/json/{SPORTSDB_API_KEY}"

# Simple thresholds for "high scoring" flags
HIGH_SCORE_THRESHOLDS = {
    "NBA": 230,
    "NFL": 55,
    "MLB": 12,
    "College": 60
}

TEAM_OVERRIDES = {
    # Helps TheSportsDB search find Rutgers more reliably
    "Rutgers": "Rutgers Scarlet Knights"
}

def _safe_int(x):
    try:
        return int(x)
    except Exception:
        return None

def _search_team_id(team_name: str):
    r = requests.get(f"{BASE_URL}/searchteams.php", params={"t": team_name}, timeout=20)
    r.raise_for_status()
    data = r.json()
    teams = data.get("teams") or []
    if not teams:
        return None
    return teams[0].get("idTeam")

def _fetch_last_events(team_id: str):
    r = requests.get(f"{BASE_URL}/eventslast.php", params={"id": team_id}, timeout=20)
    r.raise_for_status()
    return r.json().get("results") or []

def _fetch_next_events(team_id: str):
    r = requests.get(f"{BASE_URL}/eventsnext.php", params={"id": team_id}, timeout=20)
    r.raise_for_status()
    return r.json().get("events") or []

def _format_final(event):
    home = event.get("strHomeTeam", "?")
    away = event.get("strAwayTeam", "?")
    hs = _safe_int(event.get("intHomeScore"))
    as_ = _safe_int(event.get("intAwayScore"))
    date = event.get("dateEvent", "")
    if hs is None or as_ is None:
        return None
    return f"{away} {as_} @ {home} {hs} ({date})"

def _format_upcoming(event):
    home = event.get("strHomeTeam", "?")
    away = event.get("strAwayTeam", "?")
    date = event.get("dateEvent", "")
    time = event.get("strTimeLocal") or event.get("strTime") or ""
    return f"{away} vs {home} — {date} {time}".strip()

def build_sports_blocks(teams_dict: dict):
    utc_today = datetime.utcnow().date()
    utc_yesterday = utc_today - timedelta(days=1)

    yesterday_lines = []
    today_lines = []
    highlight_lines = []

    for league, teams in teams_dict.items():
        for t in teams:
            lookup = TEAM_OVERRIDES.get(t, t)
            team_id = _search_team_id(lookup)
            if not team_id:
                yesterday_lines.append(f"• {t}: (no data found)")
                today_lines.append(f"• {t}: (no data found)")
                continue

            last_events = _fetch_last_events(team_id)
            next_events = _fetch_next_events(team_id)

            # Yesterday
            y_found = False
            for e in last_events:
                d = e.get("dateEvent")
                if not d:
                    continue
                try:
                    d_date = datetime.strptime(d, "%Y-%m-%d").date()
                except Exception:
                    continue

                if d_date == utc_yesterday:
                    final = _format_final(e)
                    if final:
                        yesterday_lines.append(f"• {t}: {final}")
                        y_found = True

                        # High scoring highlight
                        hs = _safe_int(e.get("intHomeScore"))
                        as_ = _safe_int(e.get("intAwayScore"))
                        total = (hs or 0) + (as_ or 0)
                        thresh = HIGH_SCORE_THRESHOLDS.get(league)
                        if thresh and total >= thresh:
                            highlight_lines.append(f"🔥 High scoring ({league}): {final} (Total {total})")
                    break

            if not y_found:
                # If no game yesterday, show next scheduled game
                if next_events:
                    yesterday_lines.append(f"• {t}: Next — {_format_upcoming(next_events[0])}")
                else:
                    yesterday_lines.append(f"• {t}: No recent game / no upcoming found")

            # Today block (show if game date matches today UTC; otherwise next)
            t_found = False
            for e in next_events:
                d = e.get("dateEvent")
                if not d:
                    continue
                try:
                    d_date = datetime.strptime(d, "%Y-%m-%d").date()
                except Exception:
                    continue

                if d_date == utc_today:
                    today_lines.append(f"• {t}: {_format_upcoming(e)}")
                    t_found = True
                    break

            if not t_found:
                if next_events:
                    today_lines.append(f"• {t}: Next — {_format_upcoming(next_events[0])}")
                else:
                    today_lines.append(f"• {t}: No game today / no upcoming found")

    if not highlight_lines:
        highlight_lines.append("• (No automatic highlights from scores today)")

    return (
        "\n".join(yesterday_lines) if yesterday_lines else "• (No games)",
        "\n".join(today_lines) if today_lines else "• (No games)",
        "\n".join(highlight_lines)
    )
