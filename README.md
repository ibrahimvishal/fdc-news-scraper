# News Scraper → Telegram

Small VPS-hosted news monitor.

## What it does

Twice per day, the script:

1. Searches Google News, restricted to each site in the predefined website list, for every
   configured keyword.
2. Searches Google News with no site restriction, for every configured keyword.
3. Filters both to articles published in the last 2 days.
4. Deduplicates URLs during the run.
5. Resolves each Google News redirect link to the real publisher article URL.
6. Checks SQLite for URLs already posted.
7. Posts new URLs to Telegram.
8. Saves a URL only after Telegram confirms the post.

If the run fails outright (uncaught exception), it attempts to post a failure alert to the
same Telegram channel before exiting non-zero, so a broken run doesn't fail silently.

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

Lock down the file since it holds live credentials:

```bash
chmod 600 .env
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

Runs twice a day: **11:00 AM** and **9:00 PM** Maldives time (MVT, UTC+5, no DST).

Find the virtualenv's Python path:

```bash
pwd
```

Check the VPS's configured timezone first:

```bash
timedatectl
```

**If the VPS is set to `Asia/Male`**, use local times directly:

```cron
0 11 * * * /opt/news-scraper/.venv/bin/python /opt/news-scraper/run.py >> /opt/news-scraper/data/cron.log 2>&1
0 21 * * * /opt/news-scraper/.venv/bin/python /opt/news-scraper/run.py >> /opt/news-scraper/data/cron.log 2>&1
```

**If the VPS is set to UTC** (common default), convert: 11:00 MVT = 06:00 UTC, 21:00 MVT = 16:00 UTC:

```cron
0 6 * * * /opt/news-scraper/.venv/bin/python /opt/news-scraper/run.py >> /opt/news-scraper/data/cron.log 2>&1
0 16 * * * /opt/news-scraper/.venv/bin/python /opt/news-scraper/run.py >> /opt/news-scraper/data/cron.log 2>&1
```

Edit cron with:

```bash
crontab -e
```

Adjust `/opt/news-scraper` to the actual installation directory.

Set up log rotation so `cron.log` doesn't grow unbounded, e.g. `/etc/logrotate.d/news-scraper`:

```
/opt/news-scraper/data/cron.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
}
```

## Notes

The search layer uses Google News RSS for both discovery methods, with no country-edition
lock (`gl`/`ceid`), so results aren't implicitly scoped to one country's press. Google News
RSS's `after:`/`before:`/`when:` date operators were tested and found to silently return zero
results for these queries, so date filtering is done client-side on each entry's published
date instead.

Google News RSS only ever returns `news.google.com/rss/articles/...` redirect links, not the
publisher's actual URL — resolving to a browser-visible page requires client-side JavaScript,
so a raw fetch (including Telegram's own link-preview fetcher) only sees a blank "Google News"
page. The scraper resolves each redirect to the real article URL via an internal Google
endpoint before posting and before checking/recording it in SQLite, so both the posted message
and the dedupe history use the real publisher URL. This is undocumented behavior on Google's
side and could break if they change it; if it does, the scraper falls back to posting the raw
Google News redirect link rather than dropping the article.

The SQLite database intentionally stores only the URL and posting timestamp. No article content
is downloaded or stored.
