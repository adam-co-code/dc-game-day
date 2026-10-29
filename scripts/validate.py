#!/usr/bin/env python3
"""Check events.json before it goes live.

Usage: python3 scripts/validate.py [events.json] [--previous OLD_events.json]

Exits with an error (and the site is not updated) if the file is not valid JSON,
an event is missing a field, a date or time is malformed, or a sport/venue code
isn't one index.html knows about. With --previous, it also refuses an update that
suddenly drops a large share of upcoming events, which usually means a data
source broke rather than games being cancelled.
"""
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ["date", "time", "sport", "team", "opponent", "venue", "tag", "note"]
TIME_RE = re.compile(r"^(1[0-2]|[1-9]):[0-5]\d (AM|PM)$")
MAX_DROP = 0.2  # refuse if more than 20% of upcoming events disappear at once


def app_codes():
    """Read the sport and venue codes straight from index.html so there's one source of truth."""
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    sports_block = re.search(r"const SPORTS=\{(.*?)\};", html, re.S).group(1)
    venues_block = re.search(r"const V=\{(.*?)\};", html, re.S).group(1)
    sports = set(re.findall(r"(\w+):\{label", sports_block))
    venues = set(re.findall(r"(\w+):\"", venues_block))
    return sports, venues


def upcoming(events, today):
    return sum(1 for e in events if isinstance(e, dict) and str(e.get("date", "")) >= today)


def validate(path, previous=None):
    errors, warnings = [], []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        return [f"{path} is not valid JSON: {err}"], warnings

    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        return ['Top level must be {"updated": ..., "events": [...]}'], warnings
    try:
        datetime.date.fromisoformat(data.get("updated", ""))
    except (TypeError, ValueError):
        errors.append(f'"updated" must be a date like 2026-10-29, got {data.get("updated")!r}')

    sports, venues = app_codes()
    today = datetime.date.today()
    seen_ids, seen_games = set(), set()
    for i, e in enumerate(data["events"]):
        where = f"event #{i + 1}"
        if not isinstance(e, dict):
            errors.append(f"{where} is not an object")
            continue
        where += f" ({e.get('date', '?')} {e.get('team', '?')})"
        for k in REQUIRED:
            if not isinstance(e.get(k), str):
                errors.append(f'{where}: "{k}" is missing or not text')
        if any(not isinstance(e.get(k), str) for k in REQUIRED):
            continue
        try:
            d = datetime.date.fromisoformat(e["date"])
            if not (today - datetime.timedelta(days=400) <= d <= today + datetime.timedelta(days=800)):
                errors.append(f"{where}: date {e['date']} is implausibly far from today")
        except ValueError:
            errors.append(f'{where}: "{e["date"]}" is not a real date (use YYYY-MM-DD)')
        if e["time"] and not TIME_RE.match(e["time"]):
            errors.append(f'{where}: time "{e["time"]}" should look like "7:00 PM" or be ""')
        if e["sport"] not in sports:
            errors.append(f'{where}: unknown sport "{e["sport"]}" (known: {", ".join(sorted(sports))})')
        if e["venue"] not in venues and " · " not in e["venue"]:
            errors.append(f'{where}: unknown venue code "{e["venue"]}" (add it to const V in index.html, or use "Venue · City, ST")')
        if not e["team"].strip() or not e["opponent"].strip():
            errors.append(f"{where}: team and opponent can't be blank")
        if "id" in e:
            if e["id"] in seen_ids:
                errors.append(f'{where}: duplicate id "{e["id"]}"')
            seen_ids.add(e["id"])
        game = (e["date"], e["team"], e["opponent"], e["time"])
        if game in seen_games:
            warnings.append(f"{where}: listed twice")
        seen_games.add(game)

    if previous:
        try:
            old = json.loads(Path(previous).read_text(encoding="utf-8")).get("events", [])
            t = today.isoformat()
            before, after = upcoming(old, t), upcoming(data["events"], t)
            if before >= 20 and after < before * (1 - MAX_DROP):
                errors.append(f"Upcoming events dropped from {before} to {after}; refusing in case a source broke")
        except (OSError, ValueError):
            warnings.append("Couldn't read the previous file for comparison")

    return errors, warnings


def main(argv):
    args = argv[1:]
    previous = None
    if "--previous" in args:
        i = args.index("--previous")
        previous = args[i + 1]
        del args[i:i + 2]
    path = args[0] if args else str(ROOT / "events.json")
    errors, warnings = validate(path, previous)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        print(f"\n{len(errors)} problem(s) found; {path} was NOT accepted.")
        return 1
    print(f"{path} looks good.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
