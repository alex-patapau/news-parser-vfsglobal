import requests
from bs4 import BeautifulSoup
import json
import os
import logging
import time
import re
import importlib
import importlib.util
from telegram import Bot
from telegram.error import Forbidden, BadRequest
from requests.exceptions import RequestException

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

redact_filter = RedactSensitiveFilter()
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    handler.addFilter(redact_filter)

# Keep third-party transport logs quiet to reduce accidental secret exposure.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# === File paths ===
CONFIG_FILE = "bot_config.json"
NEWS_FILE = "latest_news.json"
SUBSCRIBERS_FILE = "subscribers.json"
PARSER_STATE_FILE = os.path.join(BASE_DIR, "parser_state.json")

if not load_dotenv_if_available(os.path.join(BASE_DIR, ".env")):
    logging.info("python-dotenv not found. Using built-in .env loader.")
    load_env_file(os.path.join(BASE_DIR, ".env"))

# === Load config ===
config = {}
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
else:
    logging.warning(f"{CONFIG_FILE} not found. Using default parser settings.")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Environment variable TELEGRAM_BOT_TOKEN is missing")

# Number of HTTP retry attempts before giving up (minimum 1).
MAX_ATTEMPTS = max(1, int(config.get("MAX_ATTEMPTS", 2)))
# Delay in seconds between retry attempts (minimum 0).
RETRY_DELAY = max(0, float(config.get("RETRY_DELAY", 2)))
# HTTP request timeout in seconds for requests.get (minimum 1).
REQUEST_TIMEOUT = max(1, float(config.get("REQUEST_TIMEOUT", 20)))
MIN_REQUEST_INTERVAL_SECONDS = max(0, int(config.get("MIN_REQUEST_INTERVAL_SECONDS", 900)))
CF_COOLDOWN_SECONDS = max(60, int(config.get("CF_COOLDOWN_SECONDS", 3600)))
DEBUG_MODE = str(os.getenv("DEBUG", config.get("DEBUG", "false"))).strip().lower() in {"1", "true", "yes", "on"}
CAMOUFLAGE_API_DUMP_FILE = os.path.join(BASE_DIR, "debug_api_payloads.json")
PARSER_MODE = str(config.get("PARSER_MODE", "auto")).strip().lower()
ALLOWED_PARSER_MODES = {"auto", "api", "html"}
CLOUDFLARE_RAY_ID_REGEX = re.compile(r"Cloudflare Ray ID:\s*([A-Za-z0-9]+)", re.IGNORECASE)
CLOUDFLARE_BLOCK_MARKERS = (
    "cloudflare ray id",
    "sorry, you have been blocked",
    "attention required!",
    "please enable cookies",
)

if PARSER_MODE not in ALLOWED_PARSER_MODES:
    logging.warning(
        f"Unknown PARSER_MODE='{PARSER_MODE}'. Falling back to 'auto'. Allowed: {sorted(ALLOWED_PARSER_MODES)}"
    )
    PARSER_MODE = "auto"

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


def load_parser_state():
    if not os.path.exists(PARSER_STATE_FILE):
        return {}

    try:
        with open(PARSER_STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError) as error:
        logging.warning(f"Failed to load parser state: {error}")
        return {}

    return state if isinstance(state, dict) else {}


def save_parser_state(state):
    try:
        with open(PARSER_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as error:
        logging.warning(f"Failed to save parser state: {error}")


def format_seconds(seconds):
    seconds = max(0, int(seconds))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def extract_cloudflare_ray_id(text):
    if not isinstance(text, str) or not text:
        return None

    match = CLOUDFLARE_RAY_ID_REGEX.search(text)
    return match.group(1) if match else None


def is_cloudflare_block_text(text):
    if not isinstance(text, str) or not text:
        return False

    lowered = text.lower()
    return any(marker in lowered for marker in CLOUDFLARE_BLOCK_MARKERS)


def activate_cloudflare_cooldown(reason, response_text=None):
    now = int(time.time())
    cooldown_until = now + CF_COOLDOWN_SECONDS
    ray_id = extract_cloudflare_ray_id(response_text)

    state = load_parser_state()
    state["cooldown_until"] = cooldown_until
    state["cooldown_reason"] = reason
    state["last_blocked_at"] = now
    state["last_cloudflare_ray_id"] = ray_id
    save_parser_state(state)

    ray_suffix = f", ray_id={ray_id}" if ray_id else ""
    logging.warning(
        f"Cloudflare block detected ({reason}). Cooling down for {format_seconds(CF_COOLDOWN_SECONDS)}{ray_suffix}"
    )


def should_skip_network_request():
    state = load_parser_state()
    now = int(time.time())

    cooldown_until = state.get("cooldown_until")
    if isinstance(cooldown_until, (int, float)) and cooldown_until > now:
        remaining = int(cooldown_until - now)
        reason = state.get("cooldown_reason") or "Cloudflare block"
        ray_id = state.get("last_cloudflare_ray_id")
        ray_suffix = f" ray_id={ray_id}" if ray_id else ""
        message = f"SKIP cooldown reason={reason} remaining={format_seconds(remaining)}{ray_suffix}"
        logging.warning(message)
        return message

    if isinstance(cooldown_until, (int, float)) and cooldown_until <= now:
        state.pop("cooldown_until", None)
        state.pop("cooldown_reason", None)
        save_parser_state(state)

    last_request_started_at = state.get("last_request_started_at")
    if isinstance(last_request_started_at, (int, float)) and MIN_REQUEST_INTERVAL_SECONDS > 0:
        next_allowed_at = int(last_request_started_at) + MIN_REQUEST_INTERVAL_SECONDS
        if next_allowed_at > now:
            remaining = next_allowed_at - now
            message = f"SKIP interval remaining={format_seconds(remaining)}"
            logging.info(message)
            return message

    return None


def register_request_start():
    state = load_parser_state()
    state["last_request_started_at"] = int(time.time())
    save_parser_state(state)


def log_news_preview(news_list, source):
    if not news_list:
        return

    for index, news in enumerate(news_list[:2], start=1):
        title = (news.get("title") or "").strip() if isinstance(news, dict) else ""
        link = news.get("link") if isinstance(news, dict) else None
        logging.info(f"{source}: item#{index} title='{title[:180]}' link='{link}'")

def extract_news_from_html(html_text):
    html_len = len(html_text) if html_text else 0
    logging.info(f"HTML parser: received document length={html_len}")

    soup = BeautifulSoup(html_text, "html.parser")
    news_blocks = soup.select(".news-li")[:3]  # Take only first 3
    logging.info(f"HTML parser: found {len(news_blocks)} candidate '.news-li' blocks")

    news_list = []
    for index, block in enumerate(news_blocks, start=1):
        date_tag = block.select_one(".news-date")
        title_tag = block.select_one(".renderer-content")
        link_tag = block.select_one(".news-link")

        if not date_tag or not title_tag:
            logging.warning(
                f"HTML parser: skipping block #{index} (date_tag={bool(date_tag)} title_tag={bool(title_tag)})"
            )
            continue

        date = date_tag.get_text(strip=True)
        title = title_tag.get_text(strip=True)
        link = "https://visa.vfsglobal.com" + link_tag["href"] if link_tag and link_tag.get("href") else None
        news_list.append({"date": date, "title": title, "link": link})

    logging.info(f"HTML parser: extracted {len(news_list)} final news items")

    return news_list

def fetch_page_with_camouflage(url):
    logging.info(f"Camouflage: preparing browser session for {url}")

    try:
        from camoufox.sync_api import Camoufox
    except ImportError:
        logging.error("Camoufox is not installed. Install with: python -m pip install camoufox")
        return None

    try:
        # Camoufox runs a hardened Firefox profile to reduce bot detection.
        with Camoufox(headless=True) as browser:
            logging.info("Camouflage: browser started (headless=True)")
            page = browser.new_page()
            logging.info("Camouflage: opening new page and calling page.goto(...)")
            nav_response = page.goto(url, wait_until="domcontentloaded", timeout=30000)

            if nav_response is not None:
                logging.info(
                    f"Camouflage: page.goto completed with status={nav_response.status} url={nav_response.url}"
                )
            else:
                logging.warning("Camouflage: page.goto returned no response object")

            page.wait_for_timeout(4000)
            html = page.content()
            html_len = len(html) if html else 0
            logging.info(f"Camouflage: HTML fetched successfully, length={html_len}")

            if is_cloudflare_block_text(html):
                activate_cloudflare_cooldown("camouflage_html_block", html)
                return None

            if html_len == 0:
                logging.warning("Camouflage: empty HTML content returned")

            return html
    except Exception as e:
        logging.error(f"Camouflage fallback failed: {e}")
        return None


def _extract_news_from_api_payload(payload):
    if not isinstance(payload, dict):
        return []

    items = payload.get("items", [])
    if not isinstance(items, list):
        return []

    extracted = []
    for item in items:
        if not isinstance(item, dict):
            continue

        fields = item.get("fields", {})
        sys_data = item.get("sys", {})
        if not isinstance(fields, dict):
            fields = {}
        if not isinstance(sys_data, dict):
            sys_data = {}

        title = (
            fields.get("title")
            or fields.get("headline")
            or fields.get("name")
            or fields.get("heading")
        )

        date = (
            fields.get("date")
            or fields.get("publishedDate")
            or fields.get("publicationDate")
            or fields.get("updatedAt")
            or sys_data.get("updatedAt")
            or sys_data.get("createdAt")
        )

        link = (
            fields.get("link")
            or fields.get("url")
            or fields.get("newsLink")
            or fields.get("slug")
        )

        if isinstance(link, str) and link.startswith("/"):
            link = "https://visa.vfsglobal.com" + link

        if not isinstance(title, str) or not title.strip():
            continue

        extracted.append(
            {
                "date": str(date).strip() if date is not None else "No date",
                "title": title.strip(),
                "link": link if isinstance(link, str) and link.strip() else None,
            }
        )

    return extracted


def fetch_news_via_camouflage_api(url):
    logging.info(f"Camouflage API: preparing browser session for {url}")

    try:
        from camoufox.sync_api import Camoufox
    except ImportError:
        logging.error("Camoufox is not installed. Install with: python -m pip install camoufox")
        return []

    payloads = []
    payload_debug_records = []

    try:
        with Camoufox(headless=True) as browser:
            logging.info("Camouflage API: browser started (headless=True)")
            page = browser.new_page()

            def on_response(resp):
                response_url = resp.url
                response_url_lower = response_url.lower()
                if "content_type=countrynews" not in response_url_lower and "content_type=countrynewsflash" not in response_url_lower:
                    return

                try:
                    payload = resp.json()
                except Exception as parse_error:
                    logging.warning(f"Camouflage API: failed to decode JSON from {response_url}: {parse_error}")
                    return

                total = payload.get("total") if isinstance(payload, dict) else None
                items = payload.get("items", []) if isinstance(payload, dict) else []
                items_count = len(items) if isinstance(items, list) else 0
                logging.info(
                    f"Camouflage API: endpoint={response_url} status={resp.status} total={total} items={items_count}"
                )
                payloads.append(payload)

                if DEBUG_MODE:
                    payload_debug_records.append(
                        {
                            "endpoint": response_url,
                            "status": resp.status,
                            "total": total,
                            "items": items_count,
                            "payload": payload,
                        }
                    )

            page.on("response", on_response)
            logging.info("Camouflage API: calling page.goto(...)")
            nav_response = page.goto(url, wait_until="networkidle", timeout=60000)

            if nav_response is not None:
                logging.info(
                    f"Camouflage API: page.goto completed with status={nav_response.status} url={nav_response.url}"
                )
            else:
                logging.warning("Camouflage API: page.goto returned no response object")

            page.wait_for_timeout(5000)
            page_content = page.content()
            if is_cloudflare_block_text(page_content):
                activate_cloudflare_cooldown("camouflage_api_block", page_content)
                return []
    except Exception as e:
        logging.error(f"Camouflage API fallback failed: {e}")
        return []

    collected_news = []
    for payload in payloads:
        collected_news.extend(_extract_news_from_api_payload(payload))

    # Deduplicate news while preserving order.
    unique_news = []
    seen = set()
    for news in collected_news:
        key = (news.get("date"), news.get("title"), news.get("link"))
        if key in seen:
            continue
        seen.add(key)
        unique_news.append(news)

    if DEBUG_MODE:
        debug_dump = {
            "url": url,
            "fetched_payloads": payload_debug_records,
            "extracted_news": unique_news,
        }
        try:
            with open(CAMOUFLAGE_API_DUMP_FILE, "w", encoding="utf-8") as f:
                json.dump(debug_dump, f, ensure_ascii=False, indent=2)
            logging.info(f"Camouflage API: debug payload dump written to {CAMOUFLAGE_API_DUMP_FILE}")
        except OSError as write_error:
            logging.warning(f"Camouflage API: failed to write debug dump: {write_error}")

    logging.info(f"Camouflage API: extracted {len(unique_news)} unique news items")
    log_news_preview(unique_news, "Camouflage API")
    return unique_news[:3]


def fetch_html_for_parsing(url, headers):
    response = None
    max_attempts = MAX_ATTEMPTS

    for attempt in range(1, max_attempts + 1):
        try:
            logging.info(f"HTTP attempt {attempt}/{max_attempts}: sending request")
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            logging.info(f"HTTP attempt {attempt}/{max_attempts}: status={response.status_code}")

            if is_cloudflare_block_text(response.text):
                activate_cloudflare_cooldown("requests_block_page", response.text)
                return None

            if response.status_code == 200:
                return response.text

            if response.status_code == 403:
                activate_cloudflare_cooldown("requests_status_403", response.text)
                logging.warning("Received 403 on requests path. Skipping further fallback attempts for this run.")
                return None

            logging.warning(f"Attempt {attempt}/{max_attempts}: unexpected status {response.status_code}")
        except RequestException as e:
            logging.warning(f"Attempt {attempt}/{max_attempts}: request failed: {e}")

        if attempt < max_attempts:
            time.sleep(RETRY_DELAY)

    if response is None:
        logging.error("All request attempts failed")
    else:
        logging.error(f"Failed to fetch page after retries: last status={response.status_code}")

    return None

# === Parser ===
def parse_latest_news():
    url = "https://visa.vfsglobal.com/blr/ru/pol/"
    logging.info(f"Fetching news from {url}")
    logging.info(
        "Parser settings: mode=%s debug=%s min_interval=%s cf_cooldown=%s max_attempts=%s retry_delay=%ss timeout=%ss",
        PARSER_MODE,
        DEBUG_MODE,
        format_seconds(MIN_REQUEST_INTERVAL_SECONDS),
        format_seconds(CF_COOLDOWN_SECONDS),
        MAX_ATTEMPTS,
        RETRY_DELAY,
        REQUEST_TIMEOUT,
    )

    skip_reason = should_skip_network_request()
    if skip_reason:
        return None

    register_request_start()
    
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

    if PARSER_MODE == "api":
        api_news = fetch_news_via_camouflage_api(url)
        if not api_news:
            logging.warning("Parser mode 'api': no news returned by Camouflage API")
            return []

        logging.info(f"Parsed {len(api_news)} news items via camouflage API")
        log_news_preview(api_news, "parse_latest_news")
        return api_news

    html = fetch_html_for_parsing(url, headers)
    if not html:
        logging.error("HTML source is unavailable")

        if PARSER_MODE == "html":
            return []

        logging.warning("Parser mode 'auto': trying Camouflage API because HTML is unavailable")
        api_news = fetch_news_via_camouflage_api(url)
        if not api_news:
            return []

        logging.info(f"Parsed {len(api_news)} news items via camouflage API")
        log_news_preview(api_news, "parse_latest_news")
        return api_news

    news_list = extract_news_from_html(html)
    if news_list:
        logging.info(f"Parsed {len(news_list)} news items from HTML")
        log_news_preview(news_list, "parse_latest_news")
        return news_list

    logging.warning("No items parsed from HTML")

    if PARSER_MODE == "html":
        return []

    logging.warning("Parser mode 'auto': trying Camouflage API after empty HTML parse")
    api_news = fetch_news_via_camouflage_api(url)
    if not api_news:
        return []

    logging.info(f"Parsed {len(api_news)} news items via camouflage API")
    log_news_preview(api_news, "parse_latest_news")
    return api_news

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

    if current_news is None:
        logging.info("Run finished without network activity.")
        return

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