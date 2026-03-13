import requests
import json
import os
from datetime import datetime

# URL JSON-файла с новостями
NEWS_URL = "https://d2ab400qlgxn2g.cloudfront.net/dev/spaces/xxg4p8gt3sg6/environments/master/entries?content_type=countryNews"

# Локальный файл для кэширования
CACHE_FILE = "news_cache.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

def log(msg):
    print(f"[{datetime.now()}] {msg}")

def download_news_file():
    """Download JSON file and save locally"""
    log("Downloading news JSON...")
    try:
        r = requests.get(NEWS_URL, headers=HEADERS, timeout=10)
        r.raise_for_status()
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            f.write(r.text)
        log(f"Saved news to {CACHE_FILE}")
    except requests.RequestException as e:
        log(f"Error downloading news: {e}")

def load_news_file():
    """Load news from local file"""
    if not os.path.exists(CACHE_FILE):
        log(f"No cache file found: {CACHE_FILE}")
        return []
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("items", [])

def get_latest_news(items, count=3):
    """Extract latest news items with date, title, heading, link"""
    latest = []
    for item in items[:count]:
        fields = item.get("fields", {})
        title = fields.get("title", "")
        heading = fields.get("heading", "")
        slug = fields.get("slug", "")
        date = fields.get("date", "")
        link = f"https://visa.vfsglobal.com/blr/ru/pol/news/{slug}" if slug else ""
        latest.append({
            "date": date,
            "title": title,
            "heading": heading,
            "link": link
        })
    return latest

def compare_news(old_items, new_items):
    """Return news items that are new compared to old items"""
    old_ids = {i.get("sys", {}).get("id") for i in old_items}
    new_news = [i for i in new_items if i.get("sys", {}).get("id") not in old_ids]
    return new_news

if __name__ == "__main__":
    # Сохраняем старый кэш
    old_items = load_news_file()

    # Скачиваем новый файл
    download_news_file()

    # Загружаем свежие новости
    new_items = load_news_file()
    if not new_items:
        log("No news found in the downloaded file.")
        exit(1)

    # Сравниваем и выводим новые новости
    new_news = compare_news(old_items, new_items)
    log(f"Found {len(new_news)} new news items.")

    latest_news = get_latest_news(new_items)
    for n in latest_news:
        log(f"News: {n['date']} - {n['title']}")
        print(f"Date: {n['date']}")
        print(f"Title: {n['title']}")
        print(f"Heading: {n['heading']}")
        print(f"Link: {n['link']}\n")
