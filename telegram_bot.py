import json
import os
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# === Logging ===
LOG_FILE = "bot.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(funcName)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# === File paths ===
CONFIG_FILE = "bot_config.json"
SUBSCRIBERS_FILE = "subscribers.json"
NEWS_FILE = "latest_news.json"

# === Load config ===
if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"{CONFIG_FILE} not found! Create it with your bot token.")

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)
TOKEN = config.get("TOKEN")
if not TOKEN:
    raise ValueError("Bot TOKEN is missing in bot_config.json")

# === Subscribers functions ===
def load_subscribers():
    if not os.path.exists(SUBSCRIBERS_FILE):
        return []
    if os.path.getsize(SUBSCRIBERS_FILE) == 0:  # Если файл пустой
        return []
    with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_subscribers(subscribers):
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(subscribers, f, ensure_ascii=False, indent=2)

def add_subscriber(chat_id):
    subscribers = load_subscribers()
    if chat_id not in subscribers:
        subscribers.append(chat_id)
        save_subscribers(subscribers)
        logging.info(f"Added new subscriber: {chat_id}")

def remove_subscriber(chat_id):
    subscribers = load_subscribers()
    if chat_id in subscribers:
        subscribers.remove(chat_id)
        save_subscribers(subscribers)
        logging.info(f"Removed subscriber: {chat_id}")

# === News loader ===
def load_latest_news():
    if not os.path.exists(NEWS_FILE):
        return []
    with open(NEWS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# === Telegram commands ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    add_subscriber(chat_id)
    await update.message.reply_text("✅ You have been subscribed to news updates!")
    
    # Send latest news if available
    latest_news = load_latest_news()
    if latest_news:
        await update.message.reply_text("📢 Latest news:")
        for news in latest_news:
            msg = f"🗓 {news['date']}\n{news['title']}\n🔗 {news['link']}"
            await update.message.reply_text(msg)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    remove_subscriber(chat_id)
    await update.message.reply_text("❌ You have been unsubscribed from news updates.")

# === Bot run ===
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))

    logging.info("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
# This script periodically checks the specified news website for updates in the main headline.
# If a new headline is detected, it prints the new title; otherwise, it notifies that there is no change.