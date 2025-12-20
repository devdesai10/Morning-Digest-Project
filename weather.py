import os
import json
import time
import requests

GEOCODE_URL = "https://api.openweathermap.org/geo/1.0/direct"
ONECALL_URL  = "https://api.openweathermap.org/data/3.0/onecall"

CACHE_FILE = ".geocode_cache.json"
CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 days

def _load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_cache(cache: dict):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass

def geocode(query: str, api_key: str, limit: int = 1):
    """
    Convert a location string (e.g., "New Brunswick, NJ, US") into lat/lon.
    Uses a small local cache to avoid repeated geocoding calls.
    """
    cache = _load_cache()
    key = query.strip().lower()

    now = int(time.time())
    if key in cache:
        entry = cache[key]
        if (now - entry.get("ts", 0)) < CACHE_TTL_SECONDS:
            return entry["lat"], entry["lon"]

    r = requests.get(
        GEOCODE_URL,
        params={"q": query, "limit": limit, "appid": api_key},
        timeout=20
    )
    r.raise_for_status()
    results = r.json()
    if not results:
        raise ValueError(f"Geocoding returned no results for: {query}")

    lat = results[0]["lat"]
    lon = results[0]["lon"]

    cache[key] = {"lat": lat, "lon": lon, "ts": now}
    _save_cache(cache)
    return lat, lon

def fetch_onecall(lat: float, lon: float, api_key: str):
    r = requests.get(
        ONECALL_URL,
        params={
            "lat": lat,
            "lon": lon,
            "appid": api_key,
            "units": "imperial",
            "exclude": "minutely,hourly"  # keep response smaller; still has current+daily+alerts
        },
        timeout=20
    )
    r.raise_for_status()
    return r.json()

def format_weather_block(label: str, data: dict):
    # Current
    cur = data.get("current", {})
    cur_temp = round(cur.get("temp")) if cur.get("temp") is not None else None
    feels = round(cur.get("feels_like")) if cur.get("feels_like") is not None else None
    wind = round(cur.get("wind_speed")) if cur.get("wind_speed") is not None else None
    desc = ""
    if cur.get("weather"):
        desc = (cur["weather"][0].get("description") or "").title()

    # Today (daily[0])
    daily = (data.get("daily") or [])
    today = daily[0] if daily else {}
    hi = round(today.get("temp", {}).get("max")) if today.get("temp", {}).get("max") is not None else None
    lo = round(today.get("temp", {}).get("min")) if today.get("temp", {}).get("min") is not None else None
    pop = today.get("pop")
    rain_chance = f"{round(pop * 100)}%" if isinstance(pop, (int, float)) else "—"

    # Alerts (if any)
    alerts = data.get("alerts") or []
    alert_tag = ""
    if alerts:
        # Keep it SMS-short: show the first alert event name
        alert_name = alerts[0].get("event", "Weather Alert")
        alert_tag = f" ⚠️ {alert_name}"

    parts = []
    parts.append(f"{label}: {desc}{alert_tag}".strip())
    # Example line: "Now 42° (feels 39°) | H 47° / L 33° | Rain 20% | Wind 9 mph"
    line = []
    if cur_temp is not None:
        line.append(f"Now {cur_temp}°")
    if feels is not None:
        line.append(f"(feels {feels}°)")
    if hi is not None and lo is not None:
        line.append(f"| H {hi}° / L {lo}°")
    line.append(f"| Rain {rain_chance}")
    if wind is not None:
        line.append(f"| Wind {wind} mph")
    parts.append(" ".join(line).replace("|  |", "|"))

    return "\n".join(parts)

def get_weather_multi(locations: list, api_key: str):
    """
    locations example:
      [{"label":"Home","query":"New York, NY, US"}, ...]
    """
    blocks = []
    for loc in locations:
        label = loc.get("label", "Location").strip()
        query = loc.get("query")

        if not query:
            blocks.append(f"{label}: Weather unavailable (missing query).")
            continue

        try:
            lat, lon = geocode(query, api_key)
            data = fetch_onecall(lat, lon, api_key)
            blocks.append(format_weather_block(label, data))
        except Exception as e:
            blocks.append(f"{label}: Weather unavailable ({type(e).__name__}).")

    return "\n\n".join(blocks)
