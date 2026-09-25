# News Scraper → Telegram

Small VPS-hosted news monitor.

## What it does

Twice per day, the script:

1. Checks each monitored site's own FDC tag/category page (`tags.yaml`, or `search.yaml` for
   sites without a clean tag page) for article links — the primary discovery method.
2. Searches Google News with no site restriction, for every configured keyword — a catch-all
   for coverage outside the sites in `tags.yaml`/`search.yaml`, filtered to articles published
   in the last 2 days.
3. Deduplicates URLs during the run.
4. Resolves Google News redirect links to the real publisher article URL (tag-page links are
   already real URLs, no resolution needed).
5. Checks SQLite for URLs already posted.
6. Posts new URLs to Telegram.
7. Saves a URL only after Telegram confirms the post.

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

Search keywords are in `config.yaml`. Monitored sites are configured in `tags.yaml` (each
site's FDC tag/category page URL) and `search.yaml` (site-search fallback for sites without a
clean tag page).

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
User=<deploy-user>
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

**Tag-page discovery** (`app/tags.py`) is the primary method: each site's own FDC tag/category
page is fetched (first page only, no pagination — repeat runs plus DB dedup catch up over
time) and article links are picked out by URL shape (a run of 4+ digits, or a long hyphenated
slug for sites that use slug-style URLs), not a per-site selector. This is both more precise
and has much better recall than keyword search, especially for Dhivehi-language content, since
it relies on each publication's own editorial tagging rather than Google's search index. No
date filtering is needed here — tag pages list newest-first, so it's a pure diff against the
dedupe DB.

**Google News search** (`app/search.py`) stays on as a catch-all for coverage outside the sites
in `tags.yaml`/`search.yaml`, with no country-edition lock (`gl`/`ceid`), so results aren't
implicitly scoped to one country's press. Google News RSS's `after:`/`before:`/`when:` date
operators were tested and found to silently return zero results for these queries, so date
filtering is done client-side on each entry's published date instead. Google News RSS only
ever returns `news.google.com/rss/articles/...` redirect links, not the publisher's actual URL
— resolving to a browser-visible page requires client-side JavaScript, so a raw fetch
(including Telegram's own link-preview fetcher) only sees a blank "Google News" page. The
scraper resolves each redirect to the real article URL via an internal Google endpoint before
posting and before checking/recording it in SQLite. This is undocumented behavior on Google's
side and could break if they change it; if it does, the scraper falls back to posting the raw
Google News redirect link rather than dropping the article. Tag-page URLs never need this step
— they're already the real, direct article URL.

The SQLite database intentionally stores only the URL and posting timestamp. No article content
is downloaded or stored.

## Dev/monitoring-stage flags

Two `.env` flags (both default `false`), meant to be turned off before wider team rollout:

- `RUN_SUMMARY_ENABLED=true` — posts a per-run summary (discovered/posted/already-seen/failed
  counts, plus which URLs) to the Telegram channel and appends it to `data/run.log`.
- `POST_REASON_ENABLED=true` — appends a note to each posted article explaining which method
  found it (tag/search page + site domain, or Google search + keyword).
