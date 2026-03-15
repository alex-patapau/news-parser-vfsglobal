import requests
import os
import importlib
import importlib.util


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


def load_dotenv_if_available(env_path):
    if importlib.util.find_spec("dotenv") is None:
        return False

    dotenv_module = importlib.import_module("dotenv")
    load_dotenv = getattr(dotenv_module, "load_dotenv", None)
    if load_dotenv is None:
        return False

    load_dotenv(env_path)
    return True

# Load .env file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
if not load_dotenv_if_available(ENV_PATH):
    load_env_file(ENV_PATH)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_test_message():
    """Send a test message to your Telegram chat."""
    if not TOKEN or not CHAT_ID:
        print("[ERROR] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env file.")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": "✅ Telegram bot test message from Ubuntu (.env version)"
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("[INFO] Test message sent successfully!")
        else:
            print(f"[ERROR] Failed to send message: {resp.text}")
    except Exception as e:
        print(f"[ERROR] Exception occurred: {e}")

if __name__ == "__main__":
    send_test_message()
# This script periodically checks the specified news website for updates in the main headline.
# If a new headline is detected, it prints the new title; otherwise, it notifies that there is no change.