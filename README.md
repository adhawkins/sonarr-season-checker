# Sonarr Season Completion Checker

A command-line tool that watches a [Sonarr](https://sonarr.tv/) instance and sends you an **email notification when every episode of a season has aired**. It is designed to be run periodically (e.g. from cron or Task Scheduler) so you get notified the moment a watched series' current season finishes airing.

## How it works

On each run, for every series in your config:

1. Fetches all series from Sonarr's REST API (`GET /api/v3/series`) and matches them by **TVDB ID**.
2. Fetches all episodes for the matched series (`GET /api/v3/episode?seriesId=...`).
3. Groups episodes by season number and checks each episode's `airDate`.
4. A season is considered **complete** when every one of its episodes has an air date on or before today.
5. For each newly complete season (one not already recorded in the config's `notified` list), it:
   - adds it to a pending notification batch,
   - emails you a summary, and
   - appends `{"tvdb_id": ..., "season": ...}` to the `notified` array in your config file so it is never reported again.

If no new seasons are complete, nothing is sent and the config is left untouched.

## Requirements

- Python 3.8+
- Third-party packages:
  - [`click`](https://palletsprojects.com/p/click/)
  - [`requests`](https://requests.readthedocs.io/)

Install dependencies with:

```bash
pip install click requests
```

## Installation / first run

No installation step is required — it's a single script. On the first run, if no config file exists, the script **writes a template `config.json`** and exits:

```bash
python sonarr_season_checker.py
# Config file not found. Template written to config.json. Edit it and re-run.
```

Edit the generated `config.json`, then run again.

## Configuration

The default config path is `config.json` in the current directory (override with `--config`).

```jsonc
{
  "sonarr": {
    "base_url": "http://localhost:8989",   // Sonarr root URL (trailing slash optional)
    "api_key": "..."                        // Sonarr API key (Settings → General → API Keys)
  },
  "email": {
    "to": "you@example.com",                // recipient
    "from": "sender@example.com",           // sender address
    "host": "smtp.example.com",             // SMTP server
    "port": 587,                            // SMTP port (25, 465, 587...)
    "use_ssl": false,                       // true → implicit SSL on connect; false → STARTTLS
    "subject": "Sonarr Season Complete"     // email subject line
  },
  "series": [73762, 407281],               // list of TVDB IDs to watch (integers)
  "notified": []                            // managed automatically — do not edit by hand
}
```

### Notes on config fields

| Field | Required | Notes |
|---|---|---|
| `sonarr.base_url` | Yes | Without it (or without an API key) the run aborts with an error. |
| `sonarr.api_key` | Yes | Sent as the `apiKey` query parameter on every Sonarr API call. |
| `email.*` | No | If `to`, `from`, or `host` is missing/incomplete, notifications are **printed to stdout instead of emailed**. Useful for testing without SMTP. |
| `email.use_ssl` | No | Default `false`. `true` uses implicit SSL (`SMTP_SSL`); `false` connects in plaintext and upgrades with STARTTLS. For plain port 25 relays that don't support TLS, see the troubleshooting note below. |
| `series` | Yes | **A flat list of TVDB IDs (integers).** In Sonarr: open the show under **Series** and click **Links**, then follow the **TVDB** link to the series page on `thetvdb.com`. The TVDB ID is the number in that URL (e.g. `https://thetvdb.com/series/the-good-place-73762` → `73762`). Note: the TVDB ID is **not** shown on the Edit / Manage screen, and the number in Sonarr's own browser URL (`/series/123`) is Sonarr's *internal* series ID, not the TVDB ID. Entries that are not integers (e.g. objects) will silently never match and be skipped. || `notified` | Auto-managed | One entry per already-notified `(tvdb_id, season)` pair. The script appends here after each successful notification batch. To re-notify a season, delete its entry. |

> ⚠️ **Security:** the config file contains your Sonarr API key and SMTP details in plain text. Keep it out of version control (e.g. add `config.json` to `.gitignore`) and restrict file permissions.

## Usage

```bash
python sonarr_season_checker.py [OPTIONS]
```

### Options

| Option | Default | Description |
|---|---|---|
| `--config PATH` | `config.json` | Path to the JSON config file. A missing file causes a template to be written and the run to stop. |
| `--test-email` | — | Send a test email using the `email` section of the config, then exit. Exits with status 1 if the email config is incomplete or the send fails. |
| `--verbose N` | `0` | Verbosity level: `0` = errors/notifications only, `1` = per-series and per-season progress, `2` = per-episode detail (title + air date). |

### Examples

```bash
# Normal run with quiet output
python sonarr_season_checker.py

# Run with season-level logging
python sonarr_season_checker.py --verbose 1

# Full episode-by-episode debugging
python sonarr_season_checker.py --verbose 2

# Verify your SMTP setup before the first real notification
python sonarr_season_checker.py --test-email

# Use a non-default config file
python sonarr_season_checker.py --config /path/to/my-config.json --verbose 1
```

### Sample output

`--verbose 1`, all seasons already notified:

```
Checking series TVDB 73762
  Season 0: 9 episodes
    Season 0 appears complete
    Already notified
  Season 1: 9 episodes
    Season 1 appears complete
    Already notified
```

Notification email body (one line per newly completed season):

```
The following series seasons are now complete and have been aired:
- The Good Place (TVDB 73762) Season 4
```

## Scheduling runs

The script is idempotent — it only reports each season once — so run it on a schedule.

**Linux/macOS cron (hourly):**

```cron
0 * * * * /usr/bin/python3 /path/to/sonarr_season_checker.py --config /path/to/config.json >> /var/log/sonarr-checker.log 2>&1
```

**Windows Task Scheduler:** create a task that runs `python sonarr_season_checker.py` at the desired interval (e.g. once per hour).

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `Config file not found. Template written to ...` | First run — edit the generated config and re-run. |
| `Sonarr base_url and api_key must be set in config` | Fill in both values under `sonarr`. |
| `Failed to fetch series from Sonarr: ...` | Wrong URL, unreachable host, or invalid/expired API key. Test with `curl "<base_url>/api/v3/series?apiKey=<key>"`. |
| `Series not found in Sonarr` (verbose ≥ 1) | The TVDB ID in `series` doesn't match any series in this Sonarr instance, or the entry isn't a plain integer. |
| `Email config incomplete, printing notifications:` | Email section missing values — output goes to stdout instead. Fill in `to`, `from`, and `host`. |
| `Email send failed: ...` | SMTP connection/auth problem. Verify host/port with `--test-email`; check TLS settings (see below). |
| Nothing is ever notified | Seasons only count when **all** episodes have aired; a single future-dated or missing air date keeps the season "incomplete". Check with `--verbose 2`. |

### SMTP / TLS notes

- `use_ssl: true` → connects with implicit SSL (typical for port 465).
- `use_ssl: false` → plaintext connect followed by **STARTTLS** (typical for port 587). If your relay uses plain port 25 *without* STARTTLS support, the send will fail; in that case you'd need to remove the `starttls()` call or use a TLS-capable port.
- The script does not currently support SMTP **username/password authentication** — it works with relays that accept unauthenticated mail (e.g. an internal relay). If your provider requires credentials, extend `send_email()` accordingly.

## Limitations

- Completion is based purely on **air dates**, not on whether episodes are downloaded/monitored in Sonarr.
- No built-in retry logic for transient API or SMTP failures — rely on the scheduler to run it again.
- The full series list is re-fetched from Sonarr once per configured TVDB ID each run (fine for a small watchlist; not optimized for hundreds of entries).
- `notified` state lives in the config file; back it up if you care about notification history.

## Files in this project

| File | Purpose |
|---|---|
| `sonarr_season_checker.py` | The main program. |
| `config.json` | Your live configuration (contains secrets — don't commit). |
| `probe_api.py` | Small throwaway script used to probe the Sonarr v3 API during development; not part of the tool. |
