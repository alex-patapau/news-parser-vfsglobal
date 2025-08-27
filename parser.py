import requests
from bs4 import BeautifulSoup
import json
import os
import logging
from datetime import datetime
from telegram import Bot
from telegram.error import Forbidden, BadRequest

# === Logging ===
LOG_FILE = "parser.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(funcName)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# === File paths ===
CONFIG_FILE = "bot_config.json"
NEWS_FILE = "latest_news.json"
SUBSCRIBERS_FILE = "subscribers.json"

# === Load config ===
if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"{CONFIG_FILE} not found! Create it with your bot token.")

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)
TOKEN = config.get("TOKEN")
if not TOKEN:
    raise ValueError("Bot TOKEN is missing in bot_config.json")

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
    if os.path.getsize(NEWS_FILE) == 0:  # Если файл пустой
        return []
    with open(NEWS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_latest_news(news_list):
    with open(NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(news_list, f, ensure_ascii=False, indent=2)

# === Parser ===
def parse_latest_news():
    url = "https://visa.vfsglobal.com/blr/ru/pol/"
    logging.info(f"Fetching news from {url}")
    
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/116.0.0.0 Safari/537.36"
}
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        logging.error(f"Failed to fetch page: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    news_blocks = soup.select(".news-li")[:3]  # Take only first 3

    news_list = []
    for block in news_blocks:
        date = block.select_one(".news-date").get_text(strip=True)
        title = block.select_one(".renderer-content").get_text(strip=True)
        link_tag = block.select_one(".news-link")
        link = "https://visa.vfsglobal.com" + link_tag["href"] if link_tag else None
        news_list.append({"date": date, "title": title, "link": link})

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
    if not current_news:
        logging.error("No news parsed, exiting.")
        return

    saved_news = load_latest_news()

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