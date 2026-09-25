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

## Scheduling (systemd timer)

Runs twice a day: **11:00 AM** and **9:00 PM** Maldives time (MVT, UTC+5, no DST). Deployed via
a systemd oneshot service + timer rather than cron, so runs show up in `journalctl` alongside
everything else on the host and survive a reboot (`Persistent=true` catches up a missed run).

Check the VPS's configured timezone first — if it's not UTC, adjust `OnCalendar` accordingly
(11:00 MVT = 06:00 UTC, 21:00 MVT = 16:00 UTC):

```bash
timedatectl
```

`/etc/systemd/system/fdc-news-scraper.service`:

```ini
[Unit]
Description=FDC News Scraper (Telegram press monitor)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=vishal
WorkingDirectory=/opt/fdc-news-scraper
ExecStart=/opt/fdc-news-scraper/.venv/bin/python /opt/fdc-news-scraper/run.py
TimeoutStartSec=900
StandardOutput=journal
StandardError=journal
```

`/etc/systemd/system/fdc-news-scraper.timer`:

```ini
[Unit]
Description=Run FDC News Scraper twice daily (11:00 and 21:00 MVT / 06:00 and 16:00 UTC)

[Timer]
OnCalendar=*-*-* 06:00:00
OnCalendar=*-*-* 16:00:00
Persistent=true
Unit=fdc-news-scraper.service

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fdc-news-scraper.timer

# check schedule / status
systemctl list-timers fdc-news-scraper.timer
journalctl -u fdc-news-scraper.service -n 50 --no-pager

# trigger a run manually, outside the schedule
sudo systemctl start fdc-news-scraper.service
```

`systemctl status` on a completed oneshot service reports exit code 3 ("inactive") even on
success — check the `Process: ... (code=exited, status=0/SUCCESS)` line, not the shell exit
code, to see whether the run itself succeeded.

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
