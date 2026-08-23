# flipboard

Self-hosted split-flap message board. See `flipboard-build-plan-v2.md` for the
full plan — this repo currently covers **Phase 0**, **Phase 1A**, **Phase 1B**,
and **Phase 2**.

## What's here

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
  main.py                  GET /current, POST /message, GET /queue,
                           DELETE /queue/{id}, POST /next, GET /compose
  db.py                    SQLite schema (messages, display_log)
  compose.py               Minimal text -> 6x22 grid (placeholder for Phase 3)
  selection.py             Deterministic pick: pinned > priority > least-recently-shown
  web/compose.html         Phone-friendly posting form, no framework
  tests/                   14 pytest tests

cli/
  sim.ts                   Simulate text -> board transitions from the terminal
  dump_charset.ts           Dumps the TS charset as canonical JSON

python/
  charset.py                Python mirror of engine/charset.ts, shared with service/
  verify_parity.py          Proves TS and Python agree on the charset exactly
```

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
.venv/bin/python -m pytest service/tests/                        # 14 tests

npm run dev                           # renderer at http://localhost:5173/display.html
```

With the service running (bound to `0.0.0.0`, so it's reachable from other
devices on the LAN), open `http://<this machine's LAN IP>:8000/compose`
from your phone and post a message; it shows up on the board within 5
seconds. The Vite dev server only binds to localhost, so it's for
renderer development on this machine, not phone access.

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

FastAPI + SQLite, no auth, no reverse proxy assumed. `compose.py` turns
posted text into a grid (uppercase, drop illegal characters, word-wrap,
center) — deliberately minimal; it's a stand-in for Phase 3's real layout
engine, not an attempt at it.

Selection (`selection.py`) is one deterministic rule: a pinned, eligible
message always wins and preempts immediately, even mid-dwell; otherwise
the lowest `priority` number among eligible (non-expired,
`starts_at`-reached) messages, ties going to whichever was shown longest
ago (or never). Once picked, a message holds the display for its
`dwell_seconds` before the next `GET /current` call reselects.

`GET /compose` serves a plain-HTML/JS posting form — that's what an iOS
Shortcut ("Post to Board" → Ask for Text → POST `/message`) or any
browser on the LAN hits from a phone.

## Next: Phase 3

The real layout engine (word wrap, alignment, templates) in
`compose/`, replacing `service/compose.py` wholesale. See the build
plan, §10.
