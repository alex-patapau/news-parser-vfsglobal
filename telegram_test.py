import requests
from dotenv import load_dotenv
import os

# Load .env file
load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_test_message():
    """Send a test message to your Telegram chat."""
    if not TOKEN or not CHAT_ID:
        print("[ERROR] Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID in .env file.")
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