import requests
from datetime import datetime

NEWS_API_URL = (
    "https://d2ab400qlgxn2g.cloudfront.net/dev/spaces/xxg4p8gt3sg6/"
    "environments/master/entries?content_type=countryNews"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

def log(msg):
    print(f"[{datetime.now()}] {msg}")

def fetch_news():
    log("fetch_news - Requesting news API...")
    try:
        r = requests.get(NEWS_API_URL, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        log(f"fetch_news - Received {len(items)} items before filtering")
        # Filter by locale in Python
        filtered = [i for i in items if i.get("fields", {}).get("locale") == "pol > blr > ru"]
        log(f"fetch_news - {len(filtered)} items after filtering by locale")
        return filtered
    except requests.exceptions.RequestException as e:
        log(f"fetch_news - Error fetching news: {e}")
        return []

def parse_latest_news(items, count=3):
    latest_news = []
    for item in items[:count]:
        fields = item.get("fields", {})
        title = fields.get("title", "")
        heading = fields.get("heading", "")
        slug = fields.get("slug", "")
        date = fields.get("date", "")
        link = f"https://visa.vfsglobal.com/blr/ru/pol/news/{slug}" if slug else ""
        latest_news.append({
            "date": date,
            "title": title,
            "heading": heading,
            "link": link
        })
    return latest_news

if __name__ == "__main__":
    items = fetch_news()
    if not items:
        log("main - No news fetched, exiting.")
        exit(1)

    news = parse_latest_news(items)
    for n in news:
        log(f"News: {n['date']} - {n['title']}")
        print(f"Date: {n['date']}")
        print(f"Title: {n['title']}")
        print(f"Heading: {n['heading']}")
        print(f"Link: {n['link']}\n")
