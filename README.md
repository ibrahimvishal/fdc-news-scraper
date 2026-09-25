# News Scraper → Telegram

Small VPS-hosted news monitor.

## What it does

Twice per day, the script:

1. Searches each predefined website using every configured keyword.
2. Searches general news using every configured keyword.
3. Searches both today and the previous calendar day.
4. Deduplicates URLs during the run.
5. Checks SQLite for URLs already posted.
6. Posts new URLs to Telegram.
7. Saves a URL only after Telegram confirms the post.

## Requirements

- Ubuntu VPS
- Python 3.10+
- Telegram bot
- Bot added to the target group/channel with permission to post

## Setup

```bash
git clone <your-repository>
cd news-scraper

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
nano .env
```

Set:

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

The website and keyword lists are in `config.yaml`.

## Test

```bash
source .venv/bin/activate
python run.py
```

The SQLite database will be created at:

```text
data/articles.db
```

## Cron

Find the virtualenv's Python path:

```bash
pwd
```

Then edit cron:

```bash
crontab -e
```

Example:

```cron
0 8 * * * /opt/news-scraper/.venv/bin/python /opt/news-scraper/run.py >> /opt/news-scraper/data/cron.log 2>&1
0 20 * * * /opt/news-scraper/.venv/bin/python /opt/news-scraper/run.py >> /opt/news-scraper/data/cron.log 2>&1
```

Adjust `/opt/news-scraper` to the actual installation directory.

## Notes

The search layer currently uses Google News RSS for both discovery methods. A site-restricted query is used for the predefined website list, while a normal keyword query is used for general news discovery.

The SQLite database intentionally stores only the URL and posting timestamp. No article content is downloaded or stored.
