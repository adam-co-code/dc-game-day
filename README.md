# DC Game Day Calendar

Every in-person sporting event in and around Washington, DC, as a small installable web app.

## What's in this folder

| File | What it does |
|---|---|
| `index.html` | The app: list and month views, filters, search |
| `events.json` | All the games and events. Edit this to change the schedule. |
| `manifest.json`, `icon*.png`, `icon.svg` | Let phones install it to the home screen |
| `sw.js` | Lets the app open offline with the last schedule it loaded |

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

## Updating the schedule

Edit `events.json`. Each event looks like this:

```json
{
  "date": "2026-11-01",
  "time": "8:20 PM",
  "sport": "nfl",
  "team": "Commanders",
  "opponent": "Philadelphia Eagles",
  "venue": "nw",
  "tag": "SNF",
  "note": ""
}
```

- `time`: leave `""` if not announced yet (shows "Time TBA").
- `sport`: one of `nfl`, `nhl`, `nba` (pro basketball incl. G League), `mlb`, `soc`, `ncaaf`, `ncaab`, `oth` (special events).
- `venue`: a short code defined in `index.html` (search for `const V=`), e.g. `cap` = Capital One Arena, `nw` = Northwest Stadium, `audi` = Audi Field, `nats` = Nationals Park. You can also type a full venue name like `"Bender Arena · American U, DC"`.
- Update `"updated"` at the top of the file to today's date.

Past events hide themselves automatically.
