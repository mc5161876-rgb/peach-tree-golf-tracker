# Roundwell golf tracker prototype

`golf-tracker-codex` is the V2 mobile-first Roundwell prototype, tailored to Peach Tree Golf & Country Club in Marysville, California. It combines fast personal scoring with an illustrated course atlas built from real aerial imagery. It uses Vite through the vinext starter and keeps all prototype state in the browser. There is no backend, authentication, database, or third-party API.

The untouched V1 source snapshot is stored beside this project at `C:\Users\mc516\Documents\Aries Radar\golf-tracker-codex-v1`.

## Start locally

```powershell
npm install
npm run dev
```

Open the Local URL printed by the development server (normally `http://localhost:3000/`).

## Production build

```powershell
npm run build
```

## Play it on the phone (Tailscale HTTPS)

```powershell
npm run serve:tailnet
```

This starts the production runtime if it is not already up, points `tailscale serve` at `127.0.0.1:3000`, and prints the address to open:

```
https://desktop-1ofknrj.tail98ce4e.ts.net/
```

Open that on the iPhone, then **Share → Add to Home Screen** to install it with the club crest and name.

Why HTTPS matters: browsers refuse `navigator.geolocation` on an insecure origin. Over a plain LAN address the Measure tool falls back to measuring from the tee and says so. Over this address it measures from your real position.

**Preflight.** Each check prints pass or fail by name — Tailscale running, a certificate available, a build on disk, the app healthy locally, and the tailnet address serving. If any fails, nothing is served.

**It refuses to serve a stale build.** A server holding port 3000 keeps serving the build it loaded at boot, so rebuilding underneath it produces a page whose assets 404 — or worse, one that looks fine and is silently old. If the newest file in `dist/` is newer than the running process, the script stops and tells you which PID to kill. Stop it, run the script again.

**Scope.** `tailscale serve` shares only inside your own tailnet — this is not `tailscale funnel` and nothing is reachable from the public internet. The address points at this desktop, so loading or updating the app needs the desktop awake. Nothing here runs as a service.

To stop sharing:

```powershell
& "C:\Program Files\Tailscale\tailscale.exe" serve reset
```

The `OPEN Peach Tree Golf Score Tracker` desktop shortcut is unaffected and keeps working either way.

## Mock data

- Course, holes, tee yardages, stroke indexes, and performance-tag presets: `app/data/mock-course.ts`
- Believable seeded round history: `app/data/mock-history.ts`
- Peach Tree hole cards and the course overview: `public/course/peach-tree/`
- Reproducible course-atlas generator: `scripts/generate_peach_tree_atlas.py`

## Course-data and imagery notes

- Course identity, address, and 18-hole status are verified against the official Peach Tree Golf & Country Club site.
- Tee ratings and totals are cross-checked against the USGA National Course Rating Database. Per-hole prototype yardages use the strongest current public scorecard reference and should be verified against a current physical club scorecard before production use.
- Hole imagery uses public-domain 2022 USDA National Agriculture Imagery Program aerials served by USGS The National Map.
- Hole routes are derived from OpenStreetMap geometry and carry OpenStreetMap contributor attribution under ODbL.
- All 18 holes include an AI-illustrated view derived independently from the matching real aerial card. Illustrated is the default experience; Aerial remains available as the more authoritative geometry comparison.
- Local player note for Hole 4: the current dogleg left begins earlier than the July 2022 aerial shows. The app records that caveat without inventing a replacement route.
- The course guide is illustrative and is not live GPS, a rangefinder, or a pin sheet.

## Change prototype options

Open **Prototype Lab** from the top of the app or from **Settings**. You can switch:

- Plus/minus, stroke-number, and relative-to-par score entry
- One-hole and scorecard-grid round layouts
- Private-club, modern-sports, and clean visual themes
- Manual and smart-reveal performance-tag behavior

Lab choices, the current round, profile defaults, and saved rounds persist in `localStorage`. Use **Settings → Clear / reset mock data** to restore the initial state.

## Suggested first mobile test

Start an 18-hole round from the Blue tees. Record a score, open Prototype Lab, switch to the number buttons and scorecard layout, then add a positive and negative tag. End early to see the incomplete-round confirmation and summary.
