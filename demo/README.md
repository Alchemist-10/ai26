# Sakshi — static walkthrough

A no-build, no-backend walkthrough of the citywide operations screens and agent tab. Plain HTML/CSS/JS, Leaflet
via CDN for the map, Chart.js via CDN for the density chart. Open
`index.html` directly in a browser — nothing to install or run.

## What's real vs. mocked

| Layer | Status |
|---|---|
| Kochi geography, camera coordinates | **Real** landmarks (Vytilla, Kaloor, MG Road, Marine Drive, Edapally, Palarivattom, Fort Kochi, Aluva, Thevara, Infopark) plotted on a real OpenStreetMap tile layer via Leaflet |
| Camera video feeds | Mock — colored gradient tiles, no video |
| Plates, vehicles, observations, alerts, congestion, OD flows | Fabricated, in `js/data.js`, shaped like the real event/API schema |
| Camera-wall NL search | Hardcoded keyword matcher (`js/nlp.js`), **scoped to the cameras selected in the wall** |
| Agent tab | Hardcoded tool-call simulator (`js/agent.js`) standing in for the real local-model tool-calling design — city-wide scope, not camera-scoped |
| ANPR, OCR, tracking, trajectory linking, registry | Not implemented — this is the frontend/demo layer only |

## Pages

- `index.html` — Operations overview: map, live alert feed, congestion, camera health.
- `investigation.html` — Plate trajectory search + map path, **and** the camera wall with its scoped NL query, on one page.
- `analytics.html` — Density trend chart, OD flows, congestion detail.
- `evidence.html` — Alert queue with acknowledge, mock evidence-timeline export.
- `agent.html` — The interactive agent (replaces a plain chat tab) with visible tool calls.

## Hardcoded queries

### Camera wall (`investigation.html`) — scoped to selected cameras only

The box only ever searches cameras you've checked in the wall above it, and only recognizes six patterns:

| Type this | Matches |
|---|---|
| `find a blue bus` | KL07AB1234 |
| `show me red cars` | KL05CX5678, TN22ZZ0007 (blacklisted) |
| `any white suv` | KL01XY9999 (blacklisted) |
| `grey truck` | KA03MN7788 |
| `two wheelers` / `bikes` | KL04PT1122 |
| `black auto` | KL08BZ4321 |

Anything else returns "no hardcoded handler" and lists these six. If no camera is selected, it refuses and asks you to select one — it never silently searches the whole city.

### Agent tab (`agent.html`) — city-wide, tool-calling

| Ask this | Tool called |
|---|---|
| "Where has KL07AB1234 been today?" | `find_trajectory(plate="KL07AB1234")` |
| "Any blacklisted vehicles right now?" | `get_alerts(type="blacklist")` |
| "How's traffic on NH66 near Edapally?" | `get_congestion(segment="Edapally")` |
| "List events at Vytilla in the last hour" | `list_camera_events(camera_id="cam-01", window="1h")` |
| "Why was there an alert for TN22ZZ0007?" | `get_alerts(plate="TN22ZZ0007")` |
| "Top OD routes today" | `get_od_flows()` |

Anything off this list is refused in-character ("I can only answer from the allowlisted tools in this demo") rather than guessed — matching the real design's read-only, allowlisted-tool constraint.

### Trajectory search / evidence export

Plates with a seeded trajectory: `KL07AB1234`, `KL01XY9999`, `TN22ZZ0007`, `MH12DE1433`. `TN22ZZ0007` is the impossible-travel / cloning-candidate example (Vytilla → Aluva in 2m30s). `KL01XY9999` and `TN22ZZ0007` are the two blacklist hits.

## Extending

Everything lives in `js/data.js`. Add a camera, plate, observation, alert, or congestion row there and it appears everywhere (map, wall, trajectory, agent) without touching page markup. New hardcoded queries go in `js/nlp.js` (camera wall) or `js/agent.js` (agent tab) — both are small rule tables, not a real parser.
