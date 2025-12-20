import requests

KEYWORDS = [
    "trade", "traded", "acquire", "acquired",
    "injury", "injured", "out for", "questionable", "doubtful",
    "all-star", "all star", "allstar",
    "breaking", "suspended"
]

def _flatten_team_terms(teams_dict: dict):
    terms = []
    for league, teams in teams_dict.items():
        for t in teams:
            terms.append(t.lower())
    # Add common variants you care about
    terms += ["rutgers", "scarlet knights"]
    return sorted(set(terms))

def get_important_sports_news(api_key: str, teams_dict: dict):
    """
    Pull sports headlines and filter for:
    - your team names
    - major event keywords (trade/injury/all-star/etc.)
    """
    team_terms = _flatten_team_terms(teams_dict)

    url = "https://newsapi.org/v2/top-headlines"
    params = {
        "category": "sports",
        "country": "us",
        "pageSize": 25,
        "apiKey": api_key
    }

    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        articles = r.json().get("articles") or []
    except Exception:
        return "• ⚠️ Could not fetch sports news."

    hits = []
    for a in articles:
        title = (a.get("title") or "").strip()
        source = (a.get("source") or {}).get("name") or ""
        text = title.lower()

        team_match = any(term in text for term in team_terms)
        keyword_match = any(k in text for k in KEYWORDS)

        if team_match or keyword_match:
            hits.append(f"• {title} ({source})")

    if not hits:
        return "• (No big trade/injury/all-star headlines found in top sports news.)"

    return "\n".join(hits[:6])
