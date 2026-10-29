#!/usr/bin/env python3
"""Refresh events.json from public schedule feeds.

Run by .github/workflows/update.yml every day; you can also run it locally:
    python3 scripts/update.py            # writes events.json
    python3 scripts/update.py --dry-run  # just prints what would change

Sources (all free, no key needed):
  - Capitals: NHL's own schedule API (api-web.nhle.com)
  - Nationals: MLB's own stats API (statsapi.mlb.com)
  - Everyone else: ESPN's public schedule data (site.api.espn.com)

Events the script manages carry an "id" like "espn:401812345". Events without an
"id" (races, horse show, one-off events) are hand-entered and never touched.
If a feed fails, that team's events are left exactly as they were.
"""
import datetime
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "events.json"
ET = ZoneInfo("America/New_York")
ESPN = "https://site.api.espn.com/apis/site/v2/sports/"
FIELDS = ["date", "time", "sport", "team", "opponent", "venue", "tag", "note", "id"]

# team label (as shown in the app), sport code, feed, feed team id, tag for new events
PRO = [
    ("Wizards", "nba", "basketball/nba", "wsh", ""),
    ("Mystics", "nba", "basketball/wnba", "wsh", "WNBA"),
    ("Capital City Go-Go", "nba", "basketball/nba-development", "4", "G League"),
    ("Commanders", "nfl", "football/nfl", "wsh", ""),
    ("DC Defenders", "nfl", "football/ufl", "112646", "UFL"),
    ("D.C. United", "soc", "soccer/usa.1", "193", "MLS"),
    ("Washington Spirit", "soc", "soccer/usa.nwsl", "15365", "NWSL"),
]
COLLEGE = [
    ("Maryland Terrapins", "ncaaf", "football/college-football", "120", ""),
    ("Howard Bison", "ncaaf", "football/college-football", "47", ""),
]
SCHOOLS = [  # (label prefix, ESPN id) for men's and women's basketball
    ("Maryland Terrapins", "120"), ("Georgetown", "46"), ("GW Revolutionaries", "45"),
    ("Howard Bison", "47"), ("American Eagles", "44"), ("George Mason", "2244"),
]
for name, tid in SCHOOLS:
    COLLEGE.append((f"{name} (M)", "ncaab", "basketball/mens-college-basketball", tid, ""))
    COLLEGE.append((f"{name} (W)", "ncaab", "basketball/womens-college-basketball", tid, ""))

# Venue names as feeds spell them -> venue codes in index.html (const V)
VENUES = {
    "capital one arena": "cap", "northwest stadium": "nw", "fedexfield": "nw", "audi field": "audi",
    "nationals park": "nats", "carefirst arena": "cfa", "entertainment & sports arena": "cfa",
    "secu stadium": "secu", "maryland stadium": "secu", "xfinity center": "xfin",
    "mcdonough arena": "mcd", "charles e. smith center": "smith", "smith center": "smith",
    "greene stadium": "greene", "william h. greene stadium": "greene", "burr gymnasium": "burr",
    "bender arena": "bender", "eaglebank arena": "eagle",
}
# Other places that count as "in or just outside DC" for venues not listed above
NEARBY = {
    "MD": {"College Park", "Landover", "Hyattsville", "Upper Marlboro", "Largo", "Bethesda", "Silver Spring",
           "Rockville", "Bowie", "Greenbelt", "Oxon Hill", "National Harbor", "Capitol Heights"},
    "VA": {"Arlington", "Alexandria", "Fairfax", "Falls Church", "McLean", "Tysons", "Vienna", "Leesburg"},
}


def fetch(url):
    """GET a JSON URL, retrying a couple of times on network hiccups."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dc-game-day-updater"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return None
            if attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)


def venue_code(name, city=None, state=None):
    """Return a venue code / "Name · City, ST" string, or None if the venue isn't in the DC area."""
    if not name:
        return None
    code = VENUES.get(name.strip().lower())
    if code:
        return code
    if state == "DC" or (state in NEARBY and city in NEARBY[state]):
        return f"{name} · {city}, {state}"
    return None


def local(iso_utc):
    """UTC timestamp -> (YYYY-MM-DD, "h:mm AM/PM") in Eastern time."""
    dt = datetime.datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(ET)
    return dt.date().isoformat(), dt.strftime("%I:%M %p").lstrip("0")


def event(date, time_, sport, team, opponent, venue, tag, id_):
    return {"date": date, "time": time_, "sport": sport, "team": team, "opponent": opponent,
            "venue": venue, "tag": tag, "note": "", "id": id_}


def nhl_capitals():
    today = datetime.date.today()
    start = today.year if today.month >= 7 else today.year - 1
    out = []
    for season in (f"{start}{start + 1}", f"{start + 1}{start + 2}"):
        data = fetch(f"https://api-web.nhle.com/v1/club-schedule-season/WSH/{season}") or {}
        for g in data.get("games", []):
            if g["homeTeam"]["abbrev"] != "WSH":
                continue
            venue = venue_code(g.get("venue", {}).get("default"))
            if not venue:
                continue  # e.g. preseason games in Hershey
            date, t = local(g["startTimeUTC"])
            if g.get("gameScheduleState") not in (None, "OK"):
                t = ""
            away = g["awayTeam"]
            opp = f'{away["placeName"]["default"]} {away["commonName"]["default"]}'
            tag = {1: "Preseason", 3: "Playoffs"}.get(g.get("gameType"), "")
            out.append(event(date, t, "nhl", "Capitals", opp, venue, tag, f"nhl:{g['id']}"))
    return out


def mlb_nationals():
    year = datetime.date.today().year
    out = []
    for season in (year, year + 1):
        data = fetch("https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId=120"
                     f"&season={season}&gameType=S,E,R,F,D,L,W&hydrate=venue") or {}
        for day in data.get("dates", []):
            for g in day["games"]:
                if g["teams"]["home"]["team"]["id"] != 120:
                    continue
                venue = venue_code(g.get("venue", {}).get("name"))
                if not venue or g["status"].get("detailedState") in ("Cancelled", "Postponed"):
                    continue
                _, t = local(g["gameDate"])
                if g["status"].get("startTimeTBD"):
                    t = ""
                tag = {"S": "Spring training", "E": "Exhibition"}.get(g["gameType"], "")
                if g["gameType"] in "FDLW":
                    tag = "Playoffs"
                out.append(event(g["officialDate"], t, "mlb", "Nationals",
                                 g["teams"]["away"]["team"]["name"], venue, tag, f"mlb:{g['gamePk']}"))
    return out


def espn_team(team, sport, path, tid, tag, college):
    """One team's DC-area games from ESPN (home games plus neutral-site games at local venues)."""
    games = {}
    base = f"{ESPN}{path}/teams/{tid}/schedule"
    queries = ["", "?seasontype=2", "?seasontype=3"] + (["?fixture=true"] if path.startswith("soccer") else [])
    any_ok = False
    for q in queries:
        data = fetch(base + q)
        if data is None:
            continue
        any_ok = True
        our_id = data.get("team", {}).get("id")
        for e in data.get("events", []):
            games[e["id"]] = (e, our_id)
    if not any_ok:
        raise RuntimeError(f"no schedule returned for {team}")

    out = []
    for e, our_id in games.values():
        c = e["competitions"][0]
        status = c.get("status", {}).get("type", {}).get("name", "")
        if status in ("STATUS_CANCELED", "STATUS_FORFEIT"):
            continue
        home = next(x for x in c["competitors"] if x["homeAway"] == "home")
        away = next(x for x in c["competitors"] if x["homeAway"] == "away")
        v = c.get("venue", {})
        venue = venue_code(v.get("fullName"), v.get("address", {}).get("city"), v.get("address", {}).get("state"))
        if not venue:
            continue
        if home["team"]["id"] == our_id:
            opp = away["team"]
        elif c.get("neutralSite"):
            opp = home["team"]
        else:
            continue  # we're the visitor; the home team's feed owns this game
        date, t = local(e["date"])
        if c.get("timeValid") is False or e.get("timeValid") is False:
            t = ""
        name = opp.get("location") if college else opp.get("displayName")
        name = name or opp.get("displayName") or opp.get("name") or "TBD"
        st = e.get("seasonType") or e.get("season") or {}
        playoff = st.get("type") == 3 or any(w in st.get("name", "") for w in ("Playoff", "Postseason", "Post Season"))
        etag = f"{tag} Playoffs".strip() if playoff else tag
        if status == "STATUS_POSTPONED":
            etag = "Postponed"
        out.append(event(date, t, sport, team, name, venue, etag, f"espn:{e['id']}"))
    return out


def sources():
    yield "Capitals", "NHL", nhl_capitals
    yield "Nationals", "MLB", mlb_nationals
    for team, sport, path, tid, tag in PRO:
        yield team, "ESPN", lambda a=(team, sport, path, tid, tag): espn_team(*a, college=False)
    for team, sport, path, tid, tag in COLLEGE:
        yield team, "ESPN", lambda a=(team, sport, path, tid, tag): espn_team(*a, college=True)


def describe(e):
    return f"{e['date']} {e['time'] or 'TBA'} · {e['team']} vs {e['opponent']} · {e['venue']}"


def merge(old_events, results, today):
    """Combine feed results with the existing file. Returns (events, report lines)."""
    ok_teams = {team for team, (evs, err) in results.items() if err is None}
    by_id = {e["id"]: e for e in old_events if e.get("id")}
    unsourced = [e for e in old_events if not e.get("id")]
    adopted = set()  # positions in `unsourced` matched to a feed event
    added, changed, removed = [], [], []
    seen, merged = set(), []

    def adopt(fe):
        """Match a feed game to a hand-entered entry for the same team (same date, or same opponent ±3 days)."""
        fd = datetime.date.fromisoformat(fe["date"])
        for exact in (True, False):
            for i, e in enumerate(unsourced):
                if i in adopted or e["team"] != fe["team"]:
                    continue
                if exact and e["date"] == fe["date"]:
                    hit = True
                elif not exact:
                    gap = abs((datetime.date.fromisoformat(e["date"]) - fd).days)
                    a, b = e["opponent"].lower(), fe["opponent"].lower()
                    hit = gap <= 3 and (a in b or b in a)
                else:
                    hit = False
                if hit:
                    adopted.add(i)
                    return e
        return None

    for team, (evs, err) in results.items():
        if err is not None:
            continue
        for fe in sorted(evs, key=lambda e: e["date"]):
            if fe["id"] in seen:
                continue  # same game listed by two of our teams
            seen.add(fe["id"])
            prev = by_id.get(fe["id"]) or adopt(fe)
            if prev:
                fe["tag"] = prev["tag"] or fe["tag"]
                fe["note"] = prev.get("note", "")
                fe.update({k: v for k, v in prev.items() if k not in FIELDS})  # e.g. "tickets" from tickets.py
                if not fe["time"] and prev["date"] == fe["date"]:
                    fe["time"] = prev["time"]  # a feed saying "TBA" shouldn't erase a time we already know
                diffs = [k for k in ("date", "time", "opponent", "venue") if prev.get(k) != fe[k]]
                if diffs:
                    changed.append(f"{describe(fe)} (was: " + ", ".join(f"{k} {prev.get(k) or 'TBA'}" for k in diffs) + ")")
            elif fe["date"] >= today:
                added.append(describe(fe))
            merged.append(fe)

    for e in old_events:
        if e.get("id"):
            if e["id"] in seen:
                continue
            if e["team"] in ok_teams and e["date"] >= today:
                removed.append(describe(e))  # no longer in the feed: moved, cancelled or not a DC-area game
                continue
            merged.append(e)  # feed failed this run, or a past game
        elif not any(unsourced[i] is e for i in adopted):
            merged.append(e)

    cutoff = (datetime.date.fromisoformat(today) - datetime.timedelta(days=7)).isoformat()
    merged = [e for e in merged if e["date"] >= cutoff]

    def minutes(t):
        if not t:
            return 9999
        hm, ap = t.split()
        h, m = map(int, hm.split(":"))
        return (h % 12 + (12 if ap == "PM" else 0)) * 60 + m

    merged.sort(key=lambda e: (e["date"], minutes(e["time"]), e["team"]))
    # Keep a consistent field order; hand-entered events have no "id"
    merged = [{k: e.get(k, "") for k in FIELDS if k in e or k != "id"} | e for e in merged]
    return merged, added, changed, removed


def main():
    dry = "--dry-run" in sys.argv
    old = json.loads(EVENTS.read_text(encoding="utf-8"))
    today = datetime.datetime.now(ET).date().isoformat()

    results = {}
    for team, feed, fn in sources():
        try:
            results[team] = (fn(), None)
        except Exception as err:  # one broken feed shouldn't stop the others
            results[team] = ([], f"{type(err).__name__}: {err}")
        evs, err = results[team]
        print(f"{'FAILED' if err else 'ok':6} {feed:4} {team}: " + (err or f"{sum(e['date'] >= today for e in evs)} upcoming"))

    events, added, changed, removed = merge(old["events"], results, today)
    new = {"updated": today, "events": events}

    lines = [f"## Schedule update for {today}", "",
             f"**{len(added)} added, {len(changed)} changed, {len(removed)} removed** · "
             f"{sum(e['date'] >= today for e in events)} upcoming events total", "",
             "| Source | Team | Result |", "|---|---|---|"]
    for team, feed, _ in sources():
        evs, err = results[team]
        lines.append(f"| {feed} | {team} | " + (f"❌ {err} (kept previous data)" if err else f"✅ {sum(e['date'] >= today for e in evs)} upcoming") + " |")
    for title, items in (("Added", added), ("Changed", changed), ("Removed", removed)):
        if items:
            lines += ["", f"### {title}", ""] + [f"- {x}" for x in items]
    report = "\n".join(lines)
    print("\n" + report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(report + "\n")

    if not dry:
        EVENTS.write_text(json.dumps(new, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    if all(err for _, err in results.values()):
        print("Every source failed; check the network or the feeds.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
