# flipboard

Self-hosted split-flap message board — a display made of small mechanical
tiles that flip through letters/numbers/colors one at a time to spell out a
message, the same mechanism as an old airport departure board (this project
replaces a $3,400 commercial one, a "Vestaboard," with a Raspberry Pi and a
screen). See `flipboard-build-plan-v2.md` for the full plan — this repo
covers **Phase 0** through **Phase 3**, plus 4 of 6 **Phase 4** channels
(milestone, weather, f1, mufc), a holiday channel, and the
scheduler/quiet-hours infrastructure they run on — see "Channels and quiet hours" below.

If you just want to **put a message on a board someone else already set
up**, no coding or terminal required — see "Posting a message" below.
Everything else in this README is for setting the project up or working
on its code.

## Posting a message (no terminal needed)

The board is a small always-on computer (a Raspberry Pi) on your home
network, showing whatever message the software decides is current. If
one is already running and you just want to put text on it:

1. Make sure your phone or laptop is on the same Wi-Fi as the board.
2. Open a web browser and go to:

   **http://raspberrypi.local:8000/compose**

   (If that doesn't load — some Android phones and older routers don't do
   `.local` names — use the board's IP address instead, e.g.
   `http://192.168.1.241:8000/compose`. Ask whoever set it up, or run
   `hostname -I` on the board itself.)
3. Type your message. Check **"Pin"** if you want it to stay up until
   someone unpins it — otherwise it takes its turn in rotation with
   anything else queued (weather updates, other messages, etc). Tap
   **Send**. It appears on the board within about 5 seconds.

**Make it a one-tap app (recommended).** In Safari on iPhone, open the
address above, tap the **Share** button, then **"Add to Home Screen"**.
You get an icon called *Board* that opens straight to the form with no
browser chrome around it. On Android, the same thing lives under Chrome's
**⋮** menu as **"Add to Home screen"**. This is the easiest way to use
the board day to day.

**Or a Shortcut that skips the form entirely** (iPhone, optional): open
the **Shortcuts** app → tap **+** → add an **"Ask for Text"** action →
add **"Get Contents of URL"** below it, set the URL to
`http://raspberrypi.local:8000/message`, method **POST**, request body
**JSON**, with one field `text` whose value is the **"Provided Input"**
variable from the Ask for Text step (pick it from the variable bar — don't
type it literally). Name it "Post to Board" and add it to your Home
Screen. Now it's one tap → type → done, no page load at all. You can also
say "Hey Siri, Post to Board".

**Seeing and deleting what's queued.** The same page lists every message
waiting to be shown, marked **ON NOW** for the one currently on the board
and **PINNED** where it applies, each with a **Delete** button (it asks to
confirm first). Messages posted as templates or colour grids show a decoded
preview — `WEATHER / 75F / OVERCAST` — so you can tell them apart even
though they were never plain text. Fewer messages queued means each one
comes back around sooner.

**Brightness and contrast.** The same page has two sliders. They dim the
*image* the board draws, not the monitor's backlight — this panel has no
DDC/CI (confirmed with `ddcutil`: it answers with its EDID but ignores
commands), so its real brightness is only reachable from its own buttons.
During quiet hours the panel is powered down outright instead, which is
what `deploy/panel.sh` does.

**Quiet hours**: between **8pm and 7am** the board goes dark and silent on
purpose (there's an infant in the house). Messages you post still queue up
and appear after 7am.

If you want the board to stay on past 8pm — guests over, a party, a late
evening — the same page has a **"Keep the board on until morning"** button
near the bottom. It suppresses quiet hours only until the next 7am and then
lets it resume on its own, so the board can't be left glowing all night by
someone who tapped it and went to bed. Tap **"Resume quiet hours now"** to
end it early. The setting survives a restart of the board.

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
  main.py                  GET /current, POST /message, POST /message/grid,
                           POST /compose/smart, GET /queue, DELETE /queue/{id},
                           POST /queue/{id}/unpin, POST /next,
                           GET+POST /settings/quiet-hours,
                           GET+POST /settings/display, GET /compose,
                           GET /compose/grid
  db.py                    SQLite schema (messages, display_log, settings)
  compose/                 The layout engine — normalize/wrap/align/render/
                           templates, plus art.py for colour-chip drawing.
                           See "The layout engine" below.
  selection.py             Deterministic pick: pinned first, then round-robin by
                           least-recently-shown, priority breaking ties
  config.py                is_quiet_hours() — see "Channels and quiet hours"
  settings.py              Runtime settings that survive a restart (quiet-hours
                           snooze, display brightness/contrast)
  messages.py              create_message(): shared by POST /message and channels;
                           validate_grid(): the POST /message/grid boundary check
  channels/                Scheduler + plugin interface + milestone/weather/f1/
                           mufc/holiday
  web/compose.html         Phone-friendly posting form, no framework
  web/grid.html            Color grid designer — paint all 132 cells directly
  tests/                   192 pytest tests

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

# POST /message/grid — raw 132-code array instead of text, for color
# patterns. Codes 56-62 are the 7 chips (red, orange, yellow, green,
# blue, violet, white); this fills row 0 with a red/blue stripe.
# Easier in practice: http://localhost:8000/compose/grid, a paint UI.
curl -X POST http://localhost:8000/message/grid \
  -H "Content-Type: application/json" \
  -d "{\"grid\": $(python3 -c 'print([56]*11+[60]*11+[0]*110)')}"
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

## Running it on the Raspberry Pi

This is the real deployment — the Pi boots straight into the board with no
keyboard, no login, and no terminal. It's deliberately different from the
dev setup above: **there is no Vite dev server in production.** `npm run
build` emits a static bundle to `dist/`, and the FastAPI service serves it,
so the whole board is one process on one port.

**First-time setup**, once the Pi has Node 18+, Python 3.11+, and this repo
in `~/flipboard`:

```bash
cd ~/flipboard
python3 -m venv .venv && .venv/bin/pip install -r service/requirements.txt
npm install
./deploy/install.sh
```

`install.sh` builds the renderer, installs a `systemctl --user` unit, and
appends the kiosk launcher to labwc's autostart. It needs no `sudo`, and
it's safe to re-run. Reboot to confirm the board comes back on its own.

**After changing code** (from your laptop):

```bash
rsync -az --exclude node_modules --exclude .venv --exclude dist \
  --exclude '__pycache__' --exclude service/flipboard.db \
  ./ pi-user@raspberrypi.local:~/flipboard/
ssh pi-user@raspberrypi.local 'cd ~/flipboard && npm run build && systemctl --user restart flipboard'
```

**Day-to-day commands on the Pi:**

```bash
systemctl --user status flipboard     # is it up?
systemctl --user restart flipboard    # after a config or code change
journalctl --user -u flipboard -f     # live logs
ss -lptn 'sport = :8000'              # what is actually holding the port
```

**Forcing the board to stay lit through quiet hours** (for a demo, or
while setting things up in the evening) — the service reads
`FLIPBOARD_QUIET_HOURS=off`:

```bash
mkdir -p ~/.config/systemd/user/flipboard.service.d
printf '[Service]\nEnvironment=FLIPBOARD_QUIET_HOURS=off\n' \
  > ~/.config/systemd/user/flipboard.service.d/quiet-hours-off.conf
systemctl --user daemon-reload && systemctl --user restart flipboard
```

To put the normal 8pm–7am window back, delete that one file and re-run the
last line. Prefer this over editing `service/config.py`, which is a code
change you then have to remember to revert.

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

**A code or config change seems to have no effect — but the API still
answers.** This is the nastiest one, because nothing looks broken. A
leftover manually-started `uvicorn` can still be holding `:8000`, so the
one you *meant* to run fails to bind and restarts in a loop, while `curl
/current` cheerfully answers — from the **old** process running **old**
code. Under systemd the giveaway is `Active: activating` with a climbing
`restart counter`, but `curl` returning 200 the whole time hides it.

Don't trust the fact that the port responds. Ask which process owns it:

```bash
ss -lptn 'sport = :8000'
```

That prints the actual PID. If it isn't the one systemd reports
(`systemctl --user status flipboard`), kill it and restart:

```bash
kill <the-pid-from-ss>
systemctl --user reset-failed flipboard
systemctl --user restart flipboard
```

Symptoms this explains: an environment variable that "does nothing", a
newly added route returning 404, an edit to `service/` that never shows
up. On macOS use `lsof -i :8000 -sTCP:LISTEN` instead of `ss`.

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

`POST /message/grid` takes a raw 132-code array (one per cell, ROWS×COLS)
instead of text — the equivalent of Vestaboard's raw-matrix API, for
posting a color pattern instead of wrapped text. `GET /compose/grid`
serves a click/drag paint UI over the 7 chip colors that builds that
array and posts it. A pattern and a caption aren't exclusive — letters
and chips are both just codes in the same array (the same reasoning
`engine/` already uses everywhere), so the paint UI also takes an
optional caption line that composites onto one row of whatever's
painted, all client-side, before posting the merged array through the
same endpoint. Validation (`messages.py`'s `validate_grid`) lives only
at this boundary — length must be exactly 132, every code must be
in charset range — because it's the one place codes arrive untrusted;
`create_message()`'s other callers (channels, `POST /message`'s own
`render()` output) already build valid grids by construction.

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
- **art** — colour-chip drawing. Art is written as literal rows of
  single-character palette keys, so the source looks like what it
  renders; `caption()` lays a centred line of text over one row. Used by
  the holiday channel. At 6×22 flat cells this is closer to cross-stitch
  than drawing — silhouettes read, detail doesn't.

## Channels and quiet hours

`service/channels/` — a `Channel(name, cron, run)` where `run()` returns
a `ChannelMessage(text=...)` or `ChannelMessage(grid=<a template call>)`
or `None` (nothing to post this cycle), appended to `CHANNELS`. The
scheduler (APScheduler, in-process) handles the rest, gating every
channel on quiet hours before it even runs.

Four of six are built, plus one that wasn't in the plan:

- **milestone** — a days-old counter (`banner`), 8:00am daily. No
  external API, just a reference date.
- **weather** — current conditions at a fixed location (`stat`), via
  [Open-Meteo](https://open-meteo.com) (free, keyless), refreshed every
  three hours through the day.
- **f1** — countdown to lights-out before a race, top-3 results for a
  couple of days after, via [OpenF1](https://openf1.org) (free,
  keyless). Polls hourly and decides for itself whether there's
  anything worth posting — "race weekend" isn't a fixed schedule, so
  the cron is just a polling cadence.

**Live scores.** mufc and f1 poll every five minutes. While a match or
race is actually in progress they pin a live message — the running
scoreline (`LIVE 77' / MUFC 4-1 IPSWICH`) or the current top three — so
the board shows that and nothing else until it finishes, then reverts to
the normal rotation. Polls that find an unchanged score don't post again;
they just keep the existing message alive.
- **mufc** — countdown to the next Manchester United fixture, the
  scoreline for a couple of days after one finishes, via ESPN's public
  site API (free, keyless).
- **holiday** — a greeting and a piece of colour-chip art on the day of
  thirteen festivals: Pongal, Holi, both Eids, Raksha Bandhan, Onam,
  Janmashtami, Ganesh Chaturthi, Navratri, Durga Puja, Dussehra, Diwali
  and Christmas. Diwali gets a row of diyas, Holi a scatter of thrown
  colour, Onam a pookalam, Eid a crescent and star, Christmas a tree.
  Runs at 7:30am, just after quiet hours lift, and the greeting expires
  at midnight so it doesn't linger. Most of these dates are lunar and
  move every year, so they come from a baked-in table (2026–2031)
  rather than a live lookup — see `service/channels/holiday.py` for how
  to regenerate it. The two Eid dates depend on a moon sighting and can
  land a day either side of the table.

calendar and markets aren't built — each needs something this repo
doesn't have on its own: calendar OAuth or an ICS feed URL, or a stock
watchlist. mufc was on that list too, on the assumption it needed a
football-data.org key; ESPN's public API turned out to need nothing.

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

calendar and markets, once there's an ICS feed or a watchlist to build
them against. `/compose/smart` could later get an actual Claude
call as a first-choice picker (per §11, "probe 7" — not yet run since it
needs a paid `ANTHROPIC_API_KEY`), falling back to the heuristic version
above rather than replacing it.
