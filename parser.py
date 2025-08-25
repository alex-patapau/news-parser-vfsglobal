import requests
from bs4 import BeautifulSoup
import time

URL = "https://www.bbc.co.uk"  # replace with the URL of the news section
CHECK_INTERVAL = 10  # seconds

def get_latest_title():
    resp = requests.get(URL)
    soup = BeautifulSoup(resp.text, "html.parser")
    # This is an example — adjust to match your site's HTML
    title_tag = soup.find("h1") or soup.find("title")
    return title_tag.get_text(strip=True) if title_tag else None

if __name__ == "__main__":
    last_title = None
    while True:
        try:
            title = get_latest_title()
            if title and title != last_title:
                print(f"[NEW] {title}")
                last_title = title
            else:
                print("[NO CHANGE]")
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(CHECK_INTERVAL)