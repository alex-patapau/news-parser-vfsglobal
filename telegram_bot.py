import json
import os
import logging
import re
import importlib
import importlib.util
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes


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


TOKEN_REGEX = re.compile(r"\b\d{8,}:[A-Za-z0-9_-]{20,}\b")


def redact_sensitive(text):
    return TOKEN_REGEX.sub("<REDACTED_TOKEN>", text)


class RedactSensitiveFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.msg, str):
            record.msg = redact_sensitive(record.msg)

        if isinstance(record.args, tuple):
            record.args = tuple(
                redact_sensitive(arg) if isinstance(arg, str) else arg for arg in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: redact_sensitive(value) if isinstance(value, str) else value
                for key, value in record.args.items()
            }

        return True


def load_dotenv_if_available(env_path):
    if importlib.util.find_spec("dotenv") is None:
        return False

    dotenv_module = importlib.import_module("dotenv")
    load_dotenv = getattr(dotenv_module, "load_dotenv", None)
    if load_dotenv is None:
        return False

    load_dotenv(env_path)
    return True

# === Logging ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "bot.log")
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

redact_filter = RedactSensitiveFilter()
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    handler.addFilter(redact_filter)

# Keep third-party transport logs quiet to reduce accidental secret exposure.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# === File paths ===
SUBSCRIBERS_FILE = os.path.join(BASE_DIR, "subscribers.json")
NEWS_FILE = os.path.join(BASE_DIR, "latest_news.json")

if not load_dotenv_if_available(os.path.join(BASE_DIR, ".env")):
    logging.warning("python-dotenv is not installed. Use environment export or install: python -m pip install python-dotenv")
    load_env_file(os.path.join(BASE_DIR, ".env"))

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Environment variable TELEGRAM_BOT_TOKEN is missing")

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