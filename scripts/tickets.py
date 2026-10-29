#!/usr/bin/env python3
"""Add ticket links and "from $X" prices to events.json.

Run by .github/workflows/update.yml after update.py. Needs one or both keys as
environment variables (stored as GitHub repository secrets):
    TICKETMASTER_API_KEY   Ticketmaster Discovery API "Consumer Key"
    SEATGEEK_CLIENT_ID     SeatGeek API "Client ID"
    SEATGEEK_CLIENT_SECRET SeatGeek "Client Secret" (optional; only if SeatGeek gave you one)

For each DC-area venue it downloads that seller's upcoming events, then matches
them to our games by date, venue and team/opponent names. Each match is stored as
    "tickets": [{"seller": "Ticketmaster", "url": "...", "from": 45, "checked": "2026-10-29"}]
("from" is left out when the seller doesn't publish a price). If a seller can't be
reached, the links and prices from the last successful check are kept as they were.
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "events.json"
ET = ZoneInfo("America/New_York")

# Our venue codes -> (name to search for, state)
VENUES = {
    "cap": ("Capital One Arena", "DC"), "nw": ("Northwest Stadium", "MD"), "audi": ("Audi Field", "DC"),
    "nats": ("Nationals Park", "DC"), "cfa": ("CareFirst Arena", "DC"), "secu": ("SECU Stadium", "MD"),
    "xfin": ("Xfinity Center", "MD"), "mcd": ("McDonough Arena", "DC"), "smith": ("Smith Center", "DC"),
    "greene": ("Greene Stadium", "DC"), "burr": ("Burr Gymnasium", "DC"), "bender": ("Bender Arena", "DC"),
    "eagle": ("EagleBank Arena", "VA"),
}
# Add-on listings (theme-night bundles, giveaway packs, hospitality) only win when there's no plain game listing
PROMO = re.compile(r"\bpacks?\b|bundle|package|voucher|hospitality|experience|theme night|ticket \+|\+ ", re.I)
SKIP = re.compile(r"parking|season ticket|ticket package|flex plan|mini plan|suite rental|gift card", re.I)
STOP = {"vs", "the", "and", "of", "at", "university", "college", "state", "fc", "sc", "city", "new", "st",
        "saint", "men", "mens", "women", "womens", "basketball", "football", "game", "washington", "dc", "d.c"}


def get(url, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dc-game-day-tickets"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as err:
            if err.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == tries - 1:
                raise
        time.sleep(2 + 2 ** attempt)


def words(s):
    return {w for w in re.findall(r"[a-z0-9]+", s.lower().replace("'", "")) if len(w) > 1 and w not in STOP}


def ticketmaster(key, today):
    """All upcoming Ticketmaster events at our venues, as (venue code, local date, time, name, url, min price)."""
    out = []
    for code, (name, state) in VENUES.items():
        q = urllib.parse.urlencode({"apikey": key, "keyword": name, "stateCode": state, "size": 20})
        data = get(f"https://app.ticketmaster.com/discovery/v2/venues.json?{q}")
        ids = [v["id"] for v in data.get("_embedded", {}).get("venues", [])
               if words(name) <= words(v.get("name", ""))]
        time.sleep(0.25)  # Ticketmaster allows 5 requests a second
        for vid in ids:
            for page in range(5):  # Ticketmaster stops paging at 1,000 results
                q = urllib.parse.urlencode({"apikey": key, "venueId": vid, "size": 200, "page": page,
                                            "sort": "date,asc", "startDateTime": f"{today}T00:00:00Z"})
                data = get(f"https://app.ticketmaster.com/discovery/v2/events.json?{q}")
                time.sleep(0.25)
                for e in data.get("_embedded", {}).get("events", []):
                    start = e.get("dates", {}).get("start", {})
                    prices = [p["min"] for p in e.get("priceRanges", []) if p.get("min")]
                    out.append((code, start.get("localDate"), start.get("localTime", "")[:5], e["name"], e["url"],
                                min(prices) if prices else None))
                if page + 1 >= data.get("page", {}).get("totalPages", 0):
                    break
    return out


def seatgeek(client_id, today):
    secret = os.environ.get("SEATGEEK_CLIENT_SECRET", "").strip()
    auth = {"client_id": client_id} | ({"client_secret": secret} if secret else {})
    """All upcoming SeatGeek events at our venues, in the same shape as ticketmaster()."""
    out = []
    for code, (name, state) in VENUES.items():
        q = urllib.parse.urlencode(auth | {"q": name, "state": state, "per_page": 20})
        data = get(f"https://api.seatgeek.com/2/venues?{q}")
        ids = [str(v["id"]) for v in data.get("venues", []) if words(name) <= words(v.get("name", ""))]
        for vid in ids:
            for page in range(1, 6):
                q = urllib.parse.urlencode(auth | {"venue.id": vid, "per_page": 200, "page": page,
                                            "datetime_local.gte": today, "sort": "datetime_local.asc"})
                data = get(f"https://api.seatgeek.com/2/events?{q}")
                for e in data.get("events", []):
                    dt = e.get("datetime_local", "")
                    price = (e.get("stats") or {}).get("lowest_price")
                    out.append((code, dt[:10], "" if e.get("time_tbd") else dt[11:16], e.get("title", ""), e.get("url", ""), price))
                meta = data.get("meta", {})
                if page * meta.get("per_page", 200) >= meta.get("total", 0):
                    break
    return out


def to24(t):
    if not t:
        return ""
    hm, ap = t.split()
    h, m = map(int, hm.split(":"))
    return f"{h % 12 + (12 if ap == 'PM' else 0):02d}:{m:02d}"


def best_match(ev, listings):
    """Pick the seller listing for this game, or None. Same date and venue, then the best name match."""
    team = re.sub(r" \((M|W)\)$", "", ev["team"])
    tw, ow = words(team), words(ev["opponent"])
    women = ev["team"].endswith("(W)")
    # At our own venue on the right date, one name hit is enough; elsewhere require more
    needed = 1 if ev["venue"] in VENUES else 3
    best, best_rank = None, None
    for code, date, t, name, url, price in listings:
        if date != ev["date"] or SKIP.search(name):
            continue
        if ev["venue"] in VENUES and code != ev["venue"]:
            continue
        nw = words(name)
        if ev["team"].endswith(("(M)", "(W)")) and bool(re.search(r"women", name, re.I)) != women:
            continue  # never give a men's game the women's listing, or the reverse
        score = 2 * len(ow & nw) + len(tw & nw)
        if t and ev["time"] and t == to24(ev["time"]):
            score += 1
        if score < needed:
            continue
        rank = (not PROMO.search(name), score)  # a plain game listing beats any add-on package
        if best_rank is None or rank > best_rank:
            best, best_rank = (url, price), rank
    return best


def main():
    data = json.loads(EVENTS.read_text(encoding="utf-8"))
    today = datetime.datetime.now(ET).date().isoformat()
    sellers = []
    for seller, env, fn in (("Ticketmaster", "TICKETMASTER_API_KEY", ticketmaster), ("SeatGeek", "SEATGEEK_CLIENT_ID", seatgeek)):
        key = os.environ.get(env, "").strip()
        if not key:
            print(f"skip   {seller}: no {env} secret set")
            continue
        try:
            listings = fn(key, today)
            print(f"ok     {seller}: {len(listings)} listings at DC-area venues")
            sellers.append((seller, listings))
        except Exception as err:  # keep last good links for this seller
            reason = ""
            if isinstance(err, urllib.error.HTTPError):  # sellers explain refusals in the body, e.g. "Invalid client credentials"
                try:
                    reason = " - " + json.load(err).get("message", "")[:200]
                except Exception:
                    pass
            print(f"FAILED {seller}: {type(err).__name__}: {err}{reason} (kept previous links)")

    counts = {s: [0, 0] for s, _ in sellers}  # matched, with price
    upcoming = [e for e in data["events"] if e["date"] >= today]
    for ev in upcoming:
        tix = {t["seller"]: t for t in ev.get("tickets", [])}
        for seller, listings in sellers:
            m = best_match(ev, listings)
            if m:
                url, price = m
                entry = {"seller": seller, "url": url, "checked": today}
                if price:
                    entry["from"] = round(float(price))
                    counts[seller][1] += 1
                tix[seller] = entry
                counts[seller][0] += 1
            else:
                tix.pop(seller, None)
        if tix:
            ev["tickets"] = [tix[s] for s in ("Ticketmaster", "SeatGeek") if s in tix]
        else:
            ev.pop("tickets", None)

    lines = ["", "### Tickets", "", "| Seller | Games matched | With a price |", "|---|---|---|"]
    lines += [f"| {s} | {m} of {len(upcoming)} | {p} |" for s, (m, p) in counts.items()]
    report = "\n".join(lines)
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(report + "\n")
    if sellers:
        EVENTS.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
