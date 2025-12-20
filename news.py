import requests

def get_sports_news(api_key):
    url = "https://newsapi.org/v2/top-headlines"
    params = {"category": "sports", "country": "us", "pageSize": 5, "apiKey": api_key}
    try:
        res = requests.get(url, params=params, timeout=20)
        res.raise_for_status()
        data = res.json()
        articles = data.get("articles", [])
        if not articles:
            return "No breaking news today."
        lines = []
        for a in articles:
            title = a.get("title", "")
            source = a.get("source", {}).get("name", "")
            lines.append(f"• {title} ({source})")
        return "\n".join(lines[:5])
    except Exception:
        return "⚠️ Could not fetch news."
