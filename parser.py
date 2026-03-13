import requests
from bs4 import BeautifulSoup
import json
import os
import logging
import time
from telegram import Bot
from telegram.error import Forbidden, BadRequest
from requests.exceptions import RequestException

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def load_env_file(env_path):
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

# === Logging ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "parser.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(funcName)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

# === File paths ===
CONFIG_FILE = "bot_config.json"
NEWS_FILE = "latest_news.json"
SUBSCRIBERS_FILE = "subscribers.json"

if load_dotenv:
    load_dotenv(os.path.join(BASE_DIR, ".env"))
else:
    logging.warning("python-dotenv is not installed. Use environment export or install: python -m pip install python-dotenv")
    load_env_file(os.path.join(BASE_DIR, ".env"))

# === Load config ===
config = {}
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
else:
    logging.warning(f"{CONFIG_FILE} not found. Using default parser settings.")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("Environment variable TELEGRAM_BOT_TOKEN (or TELEGRAM_TOKEN) is missing")

# Number of HTTP retry attempts before giving up (minimum 1).
MAX_ATTEMPTS = max(1, int(config.get("MAX_ATTEMPTS", 2)))
# Delay in seconds between retry attempts (minimum 0).
RETRY_DELAY = max(0, float(config.get("RETRY_DELAY", 2)))
# HTTP request timeout in seconds for requests.get (minimum 1).
REQUEST_TIMEOUT = max(1, float(config.get("REQUEST_TIMEOUT", 20)))

bot = Bot(token=TOKEN)

# === Subscribers functions ===
def load_subscribers():
    if not os.path.exists(SUBSCRIBERS_FILE):
        return []
    with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_subscribers(subscribers):
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(subscribers, f, ensure_ascii=False, indent=2)

def remove_subscriber(chat_id):
    subscribers = load_subscribers()
    if chat_id in subscribers:
        subscribers.remove(chat_id)
        save_subscribers(subscribers)
        logging.info(f"Removed inactive subscriber: {chat_id}")

# === News loader ===
def load_latest_news():
    if not os.path.exists(NEWS_FILE):
        return []
    if os.path.getsize(NEWS_FILE) == 0:  # If file is empty
        return []
    with open(NEWS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_latest_news(news_list):
    with open(NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(news_list, f, ensure_ascii=False, indent=2)

def extract_news_from_html(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    news_blocks = soup.select(".news-li")[:3]  # Take only first 3

    news_list = []
    for block in news_blocks:
        date_tag = block.select_one(".news-date")
        title_tag = block.select_one(".renderer-content")
        link_tag = block.select_one(".news-link")

        if not date_tag or not title_tag:
            continue

        date = date_tag.get_text(strip=True)
        title = title_tag.get_text(strip=True)
        link = "https://visa.vfsglobal.com" + link_tag["href"] if link_tag and link_tag.get("href") else None
        news_list.append({"date": date, "title": title, "link": link})

    return news_list

def fetch_page_with_playwright(url):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logging.error("Playwright is not installed. Install with: python -m pip install playwright")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="ru-RU",
            )
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        logging.error(f"Playwright fallback failed: {e}")
        return None

# === Parser ===
def parse_latest_news():
    url = "https://visa.vfsglobal.com/blr/ru/pol/"
    logging.info(f"Fetching news from {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://visa.vfsglobal.com/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    response = None
    max_attempts = MAX_ATTEMPTS
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200 or response.status_code == 403:
                break

            logging.warning(f"Attempt {attempt}/{max_attempts}: unexpected status {response.status_code}")
        except RequestException as e:
            logging.warning(f"Attempt {attempt}/{max_attempts}: request failed: {e}")

        if attempt < max_attempts:
            time.sleep(RETRY_DELAY)

    if response is None:
        logging.error("All request attempts failed")
        return []

    if response.status_code == 403:
        logging.warning("Received 403. Trying Playwright fallback...")
        html = fetch_page_with_playwright(url)
        if not html:
            return []

        news_list = extract_news_from_html(html)
        logging.info(f"Parsed {len(news_list)} news items via Playwright")
        return news_list

    if response.status_code != 200:
        logging.error(f"Failed to fetch page: {response.status_code}")
        return []

    news_list = extract_news_from_html(response.text)

    if not news_list:
        logging.warning("No items parsed from HTML. Trying Playwright fallback...")
        html = fetch_page_with_playwright(url)
        if not html:
            return []
        news_list = extract_news_from_html(html)
        logging.info(f"Parsed {len(news_list)} news items via Playwright")
        return news_list

    logging.info(f"Parsed {len(news_list)} news items")
    return news_list

# === Telegram sender ===
def send_updates(new_news):
    subscribers = load_subscribers()
    logging.info(f"Sending updates to {len(subscribers)} subscribers")

    for chat_id in subscribers[:]:  # Copy list to allow modifications
        try:
            for news in new_news:
                msg = f"🗓 {news['date']}\n{news['title']}\n🔗 {news['link']}"
                bot.send_message(chat_id=chat_id, text=msg)
        except (Forbidden, BadRequest) as e:
            logging.warning(f"User {chat_id} is inactive: {e}")
            remove_subscriber(chat_id)

# === Main logic ===
def main():
    current_news = parse_latest_news()
    saved_news = load_latest_news()

    if not current_news:
        if saved_news:
            logging.warning("No fresh news parsed. Keeping cached news from latest_news.json")
        else:
            logging.error("No news parsed and cache is empty, exiting.")
        return

    if current_news != saved_news:
        logging.info("News changed, updating file and sending alerts...")
        save_latest_news(current_news)
        send_updates(current_news)
    else:
        logging.info("No changes in news.")

if __name__ == "__main__":
    main()
# This script periodically checks the specified news website for updates in the main headline.
# If a new headline is detected, it prints the new title; otherwise, it notifies that there is no change.