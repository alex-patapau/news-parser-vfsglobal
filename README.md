# news-parser-vfsglobal

## Quick start

1. Create and activate virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
python -m pip install requests beautifulsoup4 python-telegram-bot camoufox python-dotenv
```

3. Configure token via environment file:

```bash
cp .env.example .env
```

Set `TELEGRAM_BOT_TOKEN` in `.env`.

4. Run parser:

```bash
python parser.py
```

## Debug mode for camouflage/API

If you need deeper diagnostics (API payload dump + extra logs), run:

```bash
DEBUG=true python parser.py
```

This writes a technical dump to `debug_api_payloads.json` in the project folder.

## Parser mode in config

Set parser strategy in `bot_config.json`:

```json
"PARSER_MODE": "auto"
```

Available values:
- `auto`: parse HTML first, then fallback to Camouflage API if needed.
- `api`: use Camouflage API only.
- `html`: use HTML only (requests + Camouflage HTML fallback on 403).

## Respectful polling recommendations

Recommended config values in `bot_config.json`:

```json
"MIN_REQUEST_INTERVAL_SECONDS": 900,
"CF_COOLDOWN_SECONDS": 3600
```

- `MIN_REQUEST_INTERVAL_SECONDS=900` means not more often than once every 15 minutes.
- `CF_COOLDOWN_SECONDS=3600` means pause for 1 hour after an explicit Cloudflare block.
- On a detected Cloudflare block (`403`, `Cloudflare Ray ID`, block page text), the parser now stops further fallback attempts for that run and waits for cooldown.

## Run bot and parser in parallel (2 terminals)

Open two terminals in the project folder.

Terminal 1 (Telegram bot):

```bash
cd /home/punk/Projects/docker/parser
source .venv/bin/activate
python telegram_bot.py
```

Terminal 2 (parser every 60 seconds):

```bash
cd /home/punk/Projects/docker/parser
source .venv/bin/activate
while true; do
	python parser.py
	sleep 900
done
```

`900` seconds is the recommended minimum external interval. Even if you run it more often, the parser now skips network requests while the internal interval/cooldown is active.
