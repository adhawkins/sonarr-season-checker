#!/usr/bin/env python3
"""
Sonarr Season Completion Checker
"""
import json
import sys
import os
from datetime import datetime, date
import smtplib
from email.mime.text import MIMEText
import click
import requests

TEMPLATE_CONFIG = {
    "sonarr": {
        "base_url": "http://localhost:8989",
        "api_key": ""
    },
    "email": {
        "to": "",
        "from": "",
        "host": "",
        "port": 587,
        "use_ssl": False,
        "subject": "Sonarr Season Complete"
    },
    "series": [
        12345
    ],
    "notified": []
}

def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_config(path, config):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)

def log(msg, verbose, level=1):
    if verbose >= level:
        print(msg)

def parse_air_date(s):
    if not s:
        return None
    try:
        # handle Z suffix
        s2 = s.replace('Z', '+00:00')
        dt = datetime.fromisoformat(s2)
        return dt.date()
    except Exception:
        try:
            return date.fromisoformat(s[:10])
        except Exception:
            return None

def send_email(to, from_addr, host, port, use_ssl, subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = to
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port) as smtp:
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as smtp:
                smtp.starttls()
                smtp.send_message(msg)
        return True
    except Exception as e:
        print(f"Email send failed: {e}")
        return False

@click.command()
@click.option('--config', default='config.json', help='Path to config file')
@click.option('--test-email', is_flag=True, help='Send test email and exit')
@click.option('--verbose', default=0, type=int, help='Verbosity level 0,1,2')
def main(config, test_email, verbose):
    if not os.path.exists(config):
        with open(config, 'w', encoding='utf-8') as f:
            json.dump(TEMPLATE_CONFIG, f, indent=2)
        print(f"Config file not found. Template written to {config}. Edit it and re-run.")
        sys.exit(0)

    cfg = load_config(config)

    if test_email:
        email_cfg = cfg.get('email', {})
        to = email_cfg.get('to')
        from_addr = email_cfg.get('from')
        host = email_cfg.get('host')
        port = email_cfg.get('port', 587)
        use_ssl = email_cfg.get('use_ssl', False)
        if not all([to, from_addr, host]):
            print("Email config incomplete for test.")
            sys.exit(1)
        ok = send_email(to, from_addr, host, port, use_ssl, "Sonarr Checker Test", "This is a test email from Sonarr Season Checker.")
        print("Test email sent" if ok else "Test email failed")
        return

    sonarr_cfg = cfg.get('sonarr', {})
    base_url = sonarr_cfg.get('base_url', '').rstrip('/')
    api_key = sonarr_cfg.get('api_key', '')
    if not base_url or not api_key:
        print("Sonarr base_url and api_key must be set in config")
        sys.exit(1)

    series_list = cfg.get('series', [])
    notified = cfg.get('notified', [])
    notified_set = {(n.get('tvdb_id'), n.get('season')) for n in notified if 'tvdb_id' in n and 'season' in n}

    today = date.today()
    pending_notifications = []

    for tvdb_id in series_list:
        if tvdb_id is None:
            continue
        log(f"Checking series TVDB {tvdb_id}", verbose, 1)

        # Get Sonarr series
        try:
            r = requests.get(f"{base_url}/api/v3/series", params={'apiKey': api_key}, timeout=15)
            r.raise_for_status()
            sonarr_series_all = r.json()
        except Exception as e:
            print(f"Failed to fetch series from Sonarr: {e}")
            continue

        sonarr_series = None
        for s in sonarr_series_all:
            if s.get('tvdbId') == tvdb_id:
                sonarr_series = s
                break
        if not sonarr_series:
            log(f"  Series not found in Sonarr", verbose, 1)
            continue

        name = sonarr_series.get('title', f'TVDB {tvdb_id}')
        sonarr_id = sonarr_series.get('id')
        season_numbers = set()
        episodes_by_season = {}

        try:
            r2 = requests.get(f"{base_url}/api/v3/episode", params={'seriesId': sonarr_id, 'apiKey': api_key}, timeout=15)
            r2.raise_for_status()
            episodes = r2.json()
        except Exception as e:
            print(f"Failed to fetch episodes: {e}")
            continue

        for ep in episodes:
            season = ep.get('seasonNumber')
            if season is None:
                continue
            season_numbers.add(season)
            episodes_by_season.setdefault(season, []).append(ep)

        for season in sorted(season_numbers):
            eps = episodes_by_season.get(season, [])
            if not eps:
                continue
            log(f"  Season {season}: {len(eps)} episodes", verbose, 1)
            all_aired = True
            for ep in eps:
                air_date_str = ep.get('airDate')
                aired = False
                air_date = parse_air_date(air_date_str)
                if air_date:
                    aired = air_date <= today
                if verbose >= 2:
                    ep_name = ep.get('title') or ep.get('episodeTitle') or 'Unnamed'
                    print(f"    Episode {ep.get('episodeNumber')} {ep_name}: airDate={air_date_str} aired={aired}")
                if not aired:
                    all_aired = False
            if all_aired:
                log(f"    Season {season} appears complete", verbose, 1)
                if (tvdb_id, season) not in notified_set:
                    pending_notifications.append({
                        'tvdb_id': tvdb_id,
                        'name': name,
                        'season': season
                    })
                    notified_set.add((tvdb_id, season))
                else:
                    log(f"    Already notified", verbose, 1)
            else:
                log(f"    Season {season} not complete", verbose, 1)

    if pending_notifications:
        body_lines = ["The following series seasons are now complete and have been aired:"]
        for n in pending_notifications:
            body_lines.append(f"- {n['name']} (TVDB {n['tvdb_id']}) Season {n['season']}")
        body = "\n".join(body_lines)

        email_cfg = cfg.get('email', {})
        to = email_cfg.get('to')
        from_addr = email_cfg.get('from')
        host = email_cfg.get('host')
        port = email_cfg.get('port', 587)
        use_ssl = email_cfg.get('use_ssl', False)
        subject = email_cfg.get('subject', 'Sonarr Season Complete')

        if to and from_addr and host:
            ok = send_email(to, from_addr, host, port, use_ssl, subject, body)
            print("Notification email sent" if ok else "Notification email failed")
        else:
            print("Email config incomplete, printing notifications:")
            print(body)

        # persist notified
        for n in pending_notifications:
            cfg['notified'].append({'tvdb_id': n['tvdb_id'], 'season': n['season']})
        save_config(config, cfg)
    else:
        log("No new completed seasons found", verbose, 1)

if __name__ == '__main__':
    main()
