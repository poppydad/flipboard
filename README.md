# flipboard

Self-hosted split-flap message board — a display made of small mechanical
tiles that flip through letters/numbers/colors one at a time to spell out a
message, the same mechanism as an old airport departure board (this project
replaces a $3,400 commercial one, a "Vestaboard," with a Raspberry Pi and a
screen). See `flipboard-build-plan-v2.md` for the full plan — this repo
covers **Phase 0** through **Phase 3**, plus 3 of 6 **Phase 4** channels
(milestone, weather, f1) and the scheduler/quiet-hours infrastructure they
run on — see "Channels and quiet hours" below.

If you just want to **put a message on a board someone else already set
up**, no coding or terminal required — see "Posting a message" below.
Everything else in this README is for setting the project up or working
on its code.

## Posting a message (no terminal needed)

The board is a small always-on computer (a Raspberry Pi) on your home
network, showing whatever message the software decides is current. If
one is already running and you just want to put text on it:

1. Make sure your phone or laptop is on the same Wi-Fi as the board.
2. Open a web browser and go to `http://<the board's address>:8000/compose`
   — ask whoever set it up for the address if you don't know it (it
   looks like `192.168.1.42`, four numbers separated by dots).
3. Type your message. Check **"Pin"** if you want it to stay up until
   someone unpins it — otherwise it takes its turn in rotation with
   anything else queued (weather updates, other messages, etc). Tap
   **Send**. It appears on the board within about 5 seconds.

**One-tap posting from an iPhone** (set up once, optional): open the
**Shortcuts** app → tap **+** for a new shortcut → add an **"Ask for
Text"** action → add a **"Get Contents of URL"** action below it, set
the URL to `http://<the board's address>:8000/message`, method
**POST**, and the request body to JSON with `{"text": "Provided Input"}`
(tap the text field and choose the "Provided Input" variable from the
Ask for Text step above it, instead of typing it literally). Name the
shortcut "Post to Board" and add it to your Home Screen — now posting
is one tap, type your message, done.

## What's here

The rest of this README is for people setting up, running, or changing
the code. If any of the terms below are unfamiliar, "Prerequisites"
right after this section explains the stack in plain language.

```
spec/charset.json        Single source of truth for the flap order (63 positions:
                          blank, A-Z, 0-9, punctuation, 7 color chips)

engine/                   Headless TypeScript engine. No DOM, no browser APIs.
  charset.ts               Loads spec/charset.json, char <-> code lookups
  cell.ts                  One cell's flap state machine
  board.ts                 132-cell grid, tick loop, flap event emitter
  index.ts                 Public API
  __tests__/               25 tests, all passing

renderer/                 Canvas 2D renderer. Consumes the engine, never the reverse.
  canvas.ts                BoardCanvas: dirty-tile redraw, leaf fold, shadow, split line
  audio.ts                 BoardAudio: per-flap click scheduling, ~24-voice cap
  kiosk.ts                 Fullscreen-on-first-gesture
  main.ts                  Wires it together, polls GET /current every 5s
  display.html              Entry point — npm run dev, open /display.html

service/                  FastAPI + SQLite. LAN only, no auth.
  main.py                  GET /current, POST /message, POST /compose/smart,
                           GET /queue, DELETE /queue/{id}, POST /queue/{id}/unpin,
                           POST /next, GET /compose
  db.py                    SQLite schema (messages, display_log)
  compose/                 The layout engine — normalize/wrap/align/render/
                           templates. See "The layout engine" below.
  selection.py             Deterministic pick: pinned > priority > least-recently-shown
  config.py                is_quiet_hours() — see "Channels and quiet hours"
  messages.py              create_message(): shared by POST /message and channels
  channels/                Scheduler + plugin interface + milestone/weather/f1
  web/compose.html         Phone-friendly posting form, no framework
  tests/                   77 pytest tests

cli/
  sim.ts                   Simulate text -> board transitions from the terminal
  dump_charset.ts           Dumps the TS charset as canonical JSON

python/
  charset.py                Python mirror of engine/charset.ts, shared with service/
  verify_parity.py          Proves TS and Python agree on the charset exactly
```

## Prerequisites

What each piece of the stack actually is, for anyone new to this
particular combination of tools:

- **The engine + renderer are TypeScript**, run with **Node.js**. The
  engine computes the flap physics; the renderer draws it to a
  `<canvas>` in a browser. **Vite** (`npm run dev`) is just the dev
  server that serves that browser page and rebuilds it on save.
- **The backend is Python**, using **FastAPI** (a web framework — it's
  what answers `GET`/`POST` requests like `/message` and `/current`)
  and **SQLite** (a database that's a single file on disk, `service/
  flipboard.db` — no separate database server to install or run).
  **APScheduler** is the library that fires the weather/F1/milestone
  channels on a cron-like schedule inside that same process.
- **pytest** and **Vitest** are the Python and TypeScript test runners,
  respectively — `pytest service/tests/` and `npm test`.

What you need installed:

- **Node.js 18 or newer** (this repo is built and tested on 22). Get it
  from [nodejs.org](https://nodejs.org), or `brew install node` on
  macOS if you use Homebrew.
- **Python 3.11 or newer**. Get it from
  [python.org](https://www.python.org/downloads/), or
  `brew install python@3.11`.
- **git**, to clone this repository, and a terminal to run commands in
  (macOS: Terminal.app, iTerm, or VS Code's built-in terminal — see
  "Testing locally in VS Code" below).

Once those are installed, everything below assumes you're in a
terminal with this repository as your current directory (`cd` into
wherever you cloned it).

## Try it

```bash
npm install
npm test                              # 25 tests
npm run sim -- "HELLO WORLD"          # watch flap counts and settle time in the terminal
npm run typecheck                     # engine + cli + renderer
python3 python/verify_parity.py       # cross-language charset check

python3 -m venv .venv
.venv/bin/pip install -r service/requirements-dev.txt
.venv/bin/uvicorn service.main:app --host 0.0.0.0 --port 8000   # the API + DB
.venv/bin/python -m pytest service/tests/                        # 77 tests

npm run dev                           # renderer at http://localhost:5173/display.html
```

With the service running (bound to `0.0.0.0`, so it's reachable from other
devices on the LAN), open `http://<this machine's LAN IP>:8000/compose`
from your phone and post a message; it shows up on the board within 5
seconds. The Vite dev server only binds to localhost, so it's for
renderer development on this machine, not phone access.

**Send test messages from the terminal** instead of the phone form —
run these with the service up and `http://localhost:5173/display.html`
open in a browser, and watch the board flap over within 5 seconds:

```bash
# Plain message
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text": "HELLO FROM THE TERMINAL", "priority": 1}'

# Pinned — preempts whatever's currently showing, even mid-dwell
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text": "PINNED TEST", "pinned": true}'

# POST /compose/smart — tries the free heuristic template picker first
# (see "The layout engine" below); falls back to a plain message if the
# text doesn't match a recognized shape. These three each hit a
# different template: countdown, stat, list.
curl -X POST http://localhost:8000/compose/smart \
  -H "Content-Type: application/json" \
  -d '{"text": "5 days until vacation"}'
curl -X POST http://localhost:8000/compose/smart \
  -H "Content-Type: application/json" \
  -d '{"text": "Outside: 72F, feels chilly"}'
curl -X POST http://localhost:8000/compose/smart \
  -H "Content-Type: application/json" \
  -d '{"text": "Groceries: milk, eggs, bread"}'
```

**Inspect and manage what's queued:**

```bash
curl http://localhost:8000/queue          # everything queued: id, text, priority, pinned, page count
curl http://localhost:8000/current        # exactly what's on the board right now, as raw cell codes
curl -X POST http://localhost:8000/next   # force-advance instead of waiting out dwell_seconds
curl -X POST http://localhost:8000/queue/3/unpin   # unpin a message so it rejoins normal rotation
curl -X DELETE http://localhost:8000/queue/3   # delete a test message by id (from /queue above)
```

**Reset to a clean slate** — the DB is a single gitignored file, so stop
uvicorn, delete it, and restart; it's recreated automatically, reseeded
with one low-priority "FLIPBOARD READY" message, same as a fresh clone:

```bash
rm service/flipboard.db
```

If a port is stuck or a server won't start, see **Troubleshooting**
below.

## Testing locally in VS Code

The repo ships `.vscode/settings.json`, `launch.json`, and
`extensions.json`, so most of this is just opening the folder — VS Code
will prompt to install the recommended extensions (Python, Pylance,
Vitest) on first open.

**1. Set up once:**

```bash
npm install
python3 -m venv .venv
.venv/bin/pip install -r service/requirements-dev.txt
```

Then run **Python: Select Interpreter** from the Command Palette
(`Cmd+Shift+P`) and pick `./.venv/bin/python` if it isn't already
selected — `settings.json` points at it by default, but VS Code
sometimes needs a nudge the first time a venv is created.

**2. Run both halves side by side.** Split the integrated terminal
(the split-pane icon in the terminal panel, or `` Cmd+\ ``) and run one
in each half:

```bash
npm run dev                                                     # left: renderer, :5173
.venv/bin/uvicorn service.main:app --reload --host 0.0.0.0 --port 8000   # right: service, :8000
```

`--reload` restarts the service automatically on file changes — worth
using here even though the "Try it" command above omits it. Cmd-click
the `http://localhost:5173` link either terminal prints to open it in
your default browser; the renderer needs a real `<canvas>` and doesn't
render in VS Code's Simple Browser.

Prefer the debugger to breakpoint into the service? Use the **Run and
Debug** panel (`Cmd+Shift+D`) and pick **"Service: uvicorn (debug,
auto-reload)"** instead of the terminal command above — same effect,
plus breakpoints.

**3. Run the tests from the Testing sidebar** (`Cmd+Shift+P` →
`Testing: Focus on Test Explorer View`, or the flask icon in the
activity bar). The Vitest extension auto-discovers `engine/__tests__/`;
the Python extension auto-discovers `service/tests/` once pytest is
enabled (already set in `settings.json`). Click any test to run it,
or the bug icon next to it to debug with breakpoints. Same tests as
`npm test` / `pytest service/tests/` on the command line — the sidebar
is just faster for iterating on one failing test.

**4. Check the whole loop actually works**: with both servers running,
open `http://localhost:5173/display.html` in a browser and either fill
out `http://localhost:8000/compose` from your phone (same Wi-Fi) or
just curl it from the integrated terminal:

```bash
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text": "TESTING FROM VS CODE", "priority": 1}'
```

The board should flap over to it within 5 seconds (the renderer's poll
interval). If it doesn't, check the uvicorn terminal for errors first —
most issues at this stage are the service not running or the wrong
port, not the renderer.

**5. Other things worth sending while testing:**

```bash
# Pin a message so it preempts whatever's currently showing
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text": "PINNED TEST", "pinned": true}'

# POST /compose/smart — same shape as /message, but tries the free
# heuristic template picker first (see "The layout engine" below).
# These three exercise countdown / stat / list; anything that doesn't
# match one of those shapes just falls back to a plain banner.
curl -X POST http://localhost:8000/compose/smart \
  -H "Content-Type: application/json" \
  -d '{"text": "5 days until vacation"}'
curl -X POST http://localhost:8000/compose/smart \
  -H "Content-Type: application/json" \
  -d '{"text": "Outside: 72F, feels chilly"}'
curl -X POST http://localhost:8000/compose/smart \
  -H "Content-Type: application/json" \
  -d '{"text": "Groceries: milk, eggs, bread"}'

# See everything queued (id, text, priority, pinned, page count)
curl http://localhost:8000/queue

# See exactly what's on the board right now, as raw cell codes
curl http://localhost:8000/current

# Force the board to advance to the next eligible message immediately,
# instead of waiting out the current one's dwell_seconds
curl -X POST http://localhost:8000/next

# Unpin a message so it rejoins normal rotation instead of staying up forever
curl -X POST http://localhost:8000/queue/3/unpin

# Delete a test message by id (from the /queue output above)
curl -X DELETE http://localhost:8000/queue/3
```

**6. Reset to a clean slate.** The DB is a single gitignored file —
stop uvicorn, delete it, restart:

```bash
rm service/flipboard.db
```

It's recreated on the next uvicorn startup, reseeded with one
low-priority "FLIPBOARD READY" message, same as a fresh clone.

## Troubleshooting

**"Port 5173/8000 is in use" / a server won't start.** Something from
an earlier run is still bound to the port — VS Code's integrated
terminal is especially prone to leaving orphaned `node`/`uvicorn`
processes behind after a window reload or a crashed debug session.
Find and kill it:

```bash
lsof -i :5173 -sTCP:LISTEN        # or :8000 for the service
# COMMAND   PID     USER   ...
# node    12345 you        ...
kill 12345                         # graceful; give it a second
lsof -i :5173 -sTCP:LISTEN         # confirm the port is free
```

If it's still listed a couple seconds later (a hung process ignoring
`SIGTERM` — this can happen to a stuck Vite dev server), force it:

```bash
kill -9 12345
```

Then start the server again as normal (`npm run dev` /
`.venv/bin/uvicorn ...`).

**The board isn't updating after I post a message.** Check three things
in order: (1) is uvicorn actually running and did it log the POST
without a traceback — a stuck/crashed service is the most common cause;
(2) `curl http://localhost:8000/current` — does it show the id you just
posted, or something else? If something else, the message you posted
is real but lower-priority than what's already showing (check
`/queue`, or `pinned: true` to preempt it, or `POST /next` to force it);
(3) is the renderer tab actually open and pointed at
`http://localhost:5173/display.html` — it polls every 5s, so give it a
moment.

**A message shows blank text in `/queue`.** Expected for anything that
matched a `/compose/smart` template (countdown/stat/list) or came from
a scheduled channel — those store a pre-built grid, not raw text, so
there's nothing to echo back. The board itself is unaffected; decode
the grid directly if you need to double-check what's on it:

```bash
.venv/bin/python3 -c "
import sqlite3, json
from service.compose import CHARSET, COLS, ROWS
conn = sqlite3.connect('service/flipboard.db')
conn.row_factory = sqlite3.Row
for row in conn.execute('SELECT id, source, grid FROM messages ORDER BY id'):
    grid = json.loads(row['grid'])
    print(f\"--- id={row['id']} source={row['source']} ---\")
    for r in range(ROWS):
        print(repr(''.join(CHARSET.char_for(c) or ' ' for c in grid[r*COLS:(r+1)*COLS])))
"
```

## What the engine actually guarantees

- `Board.setTarget(grid)` points every cell at a target code; `tick(dt)`
  advances all 132 independently.
- Duration is never set directly — it falls out of wrap distance:
  `steps = (target - current) mod N`, each step a fixed `flapMs`. A cell
  moving one letter forward settles almost instantly; a cell wrapping most
  of the way around takes proportionally longer. That's the whole mechanism
  behind the cascading settle.
- Retargeting mid-flight redirects from the cell's *live* position, not
  wherever it started. This is covered explicitly in
  `board.test.ts` ("retargeting mid-animation...") because it's the kind of
  bug that's invisible without a test — everything still animates, it just
  quietly computes the wrong number of flaps.
- Every flap fires an event (`cellIndex`, `row`, `col`, `flapIndex`,
  `timestamp`) — the renderer's canvas redraw and the audio click
  scheduling both subscribe to this stream.

## Charset

63 flap positions: `0` blank, `1-26` A-Z, `27-36` 0-9, `37-55` punctuation
(`. , : ; ! ? ' " # $ ( ) - + & = / ° %`), `56-62` seven color chips (red,
orange, yellow, green, blue, violet, white). Order is physical — array index
*is* flap position — so reordering `spec/charset.json` is a breaking change
and should bump `version`.

Both `engine/charset.ts` and `python/charset.py` load the same JSON file and
enforce the same contiguity and no-duplicate-character rules.
`python/verify_parity.py` runs both loaders and diffs their output; it's
green right now, and it should stay in CI once there is one.

## The renderer

Canvas 2D, dirty-tile redraw — only cells with `remaining > 0` (plus the
one frame a cell settles) get touched, so a full-board transition is 132
dirty tiles for a moment and a clock tick is two.

Each tile splits at the midline: static top shows the incoming code,
static bottom shows the outgoing code, and a leaf rotates 0→180° between
them (`scaleY = |cos θ|`), swapping which face it draws at the 90°
edge-on point. A gradient fold shadow and an always-visible split line
sit on top — without them the board reads as a font, not a mechanism.

There's no recorded click sample yet, so `audio.ts` synthesizes a short
decaying-noise burst into an `AudioBuffer` at startup and schedules one
per flap event (jittered gain/pitch, ~24-voice cap, drop past the cap
rather than clip). `BoardAudio.setGain(0)` is a hard off-switch, driven by
`sound_enabled` in the `/current` payload.

`main.ts` polls `GET /current` every 5s and checks `charset_version`
against its own before applying a payload — a mismatch is logged and
ignored rather than shown wrong. In dev, Vite proxies API routes to the
FastAPI service on :8000 so the two stay same-origin, matching how
they'd be served together in production.

## The service

FastAPI + SQLite, no auth, no reverse proxy assumed.

Selection (`selection.py`) is one deterministic rule: a pinned, eligible
message always wins and preempts immediately, even mid-dwell; otherwise
the lowest `priority` number among eligible (non-expired,
`starts_at`-reached) messages, ties going to whichever was shown longest
ago (or never). Once picked, a message holds the display for its
`dwell_seconds` before the next `GET /current` call reselects.

`GET /compose` serves a plain-HTML/JS posting form — that's what an iOS
Shortcut ("Post to Board" → Ask for Text → POST `/message`) or any
browser on the LAN hits from a phone.

A message that overflows 6 rows doesn't truncate — `POST /message` calls
the layout engine's `render()`, gets back multiple pages, and inserts one
`messages` row per page with `dwell_seconds` divided across them (floor
20s each). No schema change needed: the existing least-recently-shown
tie-break naturally cycles same-priority rows in sequence forever, which
is exactly "linked pages" behavior for free.

## The layout engine

`service/compose/` (build plan §10) turns arbitrary text into one or more
6×22 grids, operating on charset codes the whole way through — never
strings mid-pipeline — so a color chip word-wraps exactly like a letter,
no special-casing required.

- **normalize** — uppercase, collapse whitespace runs, drop illegal
  characters outright (no placeholder box), map a small set of emoji to
  the nearest color chip, treat explicit `\n` as a forced line break.
- **wrap** — never breaks mid-word unless the word itself exceeds 22
  columns (then hard-breaks, no hyphen).
- **align** — centers both axes; on an odd leftover, floor-division
  padding biases the content toward the top-left automatically.
- **render** — orchestrates the above and paginates content over 6 lines
  into multiple linked grids instead of dropping it.
- **templates** — `banner`, `stat`, `list`, `countdown`, `chips` (a solid
  color-chip border framing centered text).

## Channels and quiet hours

`service/channels/` — a `Channel(name, cron, run)` where `run()` returns
a `ChannelMessage(text=...)` or `ChannelMessage(grid=<a template call>)`
or `None` (nothing to post this cycle), appended to `CHANNELS`. The
scheduler (APScheduler, in-process) handles the rest, gating every
channel on quiet hours before it even runs.

Three of six are built:

- **milestone** — a days-old counter (`banner`), 8:00am daily. No
  external API, just a reference date.
- **weather** — current conditions at a fixed location (`stat`), via
  [Open-Meteo](https://open-meteo.com) (free, keyless), 6:30am and
  4:00pm.
- **f1** — countdown to lights-out before a race, top-3 results for a
  couple of days after, via [OpenF1](https://openf1.org) (free,
  keyless). Polls hourly and decides for itself whether there's
  anything worth posting — "race weekend" isn't a fixed schedule, so
  the cron is just a polling cadence.

calendar, mufc, and markets aren't built — each needs something this
repo doesn't have on its own: calendar OAuth or an ICS feed URL, a
football data API key, or a stock watchlist.

Quiet hours is fully wired regardless of which channels exist:
`service/config.py`'s `is_quiet_hours()` (8:00pm–7:00am, the
household's real schedule) does two things — `GET /current` reports
`sound_enabled: false` and `brightness: 0.0`
during quiet hours, and `selection.py` excludes every non-pinned message
from consideration, so only a pinned message can show and the board
goes blank rather than displaying something inappropriate at 2am. This
also means a scheduled channel firing during quiet hours never gets a
chance to post — `run_channel()` checks first and skips entirely.

`POST /compose/smart` (build plan §11) takes free text and tries a free
heuristic template picker (`service/compose/smart.py`) before falling
back to a plain wrapped message — no Claude call, no API key, no cost.
It recognizes countdown phrasing ("5 days until vacation"), label:value
stats ("Outside: 72F, feels chilly"), and lists (comma- or newline-
separated items); anything else falls straight through to the same path
`POST /message` already uses, so it's never worse than `/message`, only
sometimes better.

## Next

calendar, mufc, and markets, once there's an ICS feed/API key/watchlist
to build them against. `/compose/smart` could later get an actual Claude
call as a first-choice picker (per §11, "probe 7" — not yet run since it
needs a paid `ANTHROPIC_API_KEY`), falling back to the heuristic version
above rather than replacing it.
