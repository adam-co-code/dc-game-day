# DC Game Day Calendar

Every in-person sporting event in and around Washington, DC, as a small installable web app.

## What's in this folder

| File | What it does |
|---|---|
| `index.html` | The app: list and month views, filters, search |
| `events.json` | All the games and events. Edit this to change the schedule. |
| `manifest.json`, `icon*.png`, `icon.svg` | Let phones install it to the home screen |
| `sw.js` | Lets the app open offline with the last schedule it loaded |
| `scripts/update.py` | Pulls the latest schedules from the NHL, MLB and ESPN feeds into `events.json` |
| `scripts/validate.py` | Checks `events.json` for mistakes before it goes live |
| `.github/workflows/` | Runs the two scripts above on GitHub automatically |

No build step, no server code, no database. Any static host works.

## Put it online (pick one)

**Netlify Drop (fastest, no account setup beyond sign-in)**
1. Go to https://app.netlify.com/drop
2. Drag this whole folder onto the page.
3. You get a live link in a few seconds. Rename the site or add your own domain under Site settings.

**GitHub Pages (best if you want automatic updates)**
1. Create a new repository on GitHub, e.g. `dc-game-day`.
2. Upload every file in this folder to it.
3. Settings → Pages → Source: "Deploy from a branch", branch `main`, folder `/ (root)`.
4. Your app is at `https://<your-username>.github.io/dc-game-day/`.

**Cloudflare Pages or Vercel** work the same way: create a project, point it at this folder or the GitHub repo, no build command, output directory `/`.

## Install on your phone

Open the link in Safari (iPhone) → Share → **Add to Home Screen**, or in Chrome (Android) → menu → **Install app**.

## How the schedule stays up to date

Every morning (about 6 AM Eastern) GitHub runs **Update schedule**, which:

1. Downloads the latest schedules (all free, no keys):
   - **Capitals** from the NHL's schedule API
   - **Nationals** from MLB's stats API
   - **Everyone else** from ESPN's public schedule data: Wizards, Mystics, Capital City Go-Go, Commanders, DC Defenders, D.C. United, Washington Spirit, Maryland and Howard football, and men's and women's basketball for Maryland, Georgetown, GW, Howard, American and George Mason
2. Keeps only games at DC-area venues (home games, plus neutral-site games in the area).
3. Checks the result with `scripts/validate.py`. If anything looks wrong, nothing is published.
4. Saves `events.json`, and GitHub Pages republishes the site a minute later.

**Seeing what happened:** open the repo's **Actions** tab → **Update schedule** → pick a run. The summary lists every source (✅ or ❌) and each game that was added, changed or removed.

**Running it right now:** Actions → **Update schedule** → **Run workflow**.

**If a source fails**, that team's games are left exactly as they were and the run shows a ❌ for it; the other teams still update. If upcoming games suddenly drop by more than 20%, the whole update is refused, in case a feed broke.

**Heads-up:** GitHub pauses scheduled jobs in a repo that has had no activity for 60 days. The daily update commits keep it active, but if it ever pauses, GitHub shows a button on the Actions tab to turn it back on.

## Editing the schedule by hand

Edit `events.json` (on GitHub: open the file → pencil icon → **Commit changes**). Each event looks like this:

```json
{
  "date": "2026-11-01",
  "time": "8:20 PM",
  "sport": "nfl",
  "team": "Commanders",
  "opponent": "Philadelphia Eagles",
  "venue": "nw",
  "tag": "SNF",
  "note": "",
  "id": "espn:401873168"
}
```

- `time`: leave `""` if not announced yet (shows "Time TBA").
- `sport`: one of `nfl` (pro football, incl. UFL), `nhl`, `nba` (pro basketball incl. WNBA and G League), `mlb`, `soc`, `ncaaf`, `ncaab`, `oth` (special events).
- `venue`: a short code defined in `index.html` (search for `const V=`), e.g. `cap` = Capital One Arena, `nw` = Northwest Stadium, `audi` = Audi Field, `nats` = Nationals Park. You can also type a full venue name like `"Bender Arena · American U, DC"`.
- `tag` and `note`: optional extra labels. The daily update keeps whatever you put here.
- `id`: **only on games the daily update manages.** It tells the update which feed game this is. Don't add one to events you enter yourself, and don't copy one between events.

Events **without** an `id` (races, the horse show, one-off events like the Capital Showcase) are yours: the update never changes or removes them. If you hand-enter a game for a team the update covers (say, a newly announced Wizards game), the update will find it by team and date, take it over, and keep your tag and note.

Events **with** an `id` can still be edited, but the feed wins on date, time, opponent and venue. Your `tag` and `note` stick.

After you commit, GitHub runs **Check schedule file**. A green ✅ next to your commit means it's fine; a red ❌ means there's a mistake. Click it to see exactly which event and field. Past events hide themselves automatically, and the daily update clears out events more than a week old.
