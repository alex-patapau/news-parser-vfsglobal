# news-parser-vfsglobal

## Quick start

1. Create and activate virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
python -m pip install requests beautifulsoup4 python-telegram-bot playwright python-dotenv
python -m playwright install chromium
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
