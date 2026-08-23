# flipboard — project context

Self-hosted split-flap message board, replacing a $3,400 Vestaboard. Full
plan is in `flipboard-build-plan-v2.md` at the repo root — read that first,
it has the phase breakdown, the bill of materials, and the risk table.

## Where things stand

**Phase 0 (charset spec), Phase 1A (headless engine), Phase 1B (canvas
renderer), Phase 2 (service + phone posting), and Phase 3 (layout engine)
are done and green. Phase 4 is partially done — see below.**

```
npm install
npm test                          # 25/25 passing
npm run sim -- "HELLO WORLD"      # CLI sim: flap counts + settle time
python3 python/verify_parity.py   # TS/Python charset agreement check
npm run typecheck                 # engine + cli + renderer, clean
npm run dev                       # Vite dev server, open /display.html

python3 -m venv .venv && .venv/bin/pip install -r service/requirements-dev.txt
.venv/bin/uvicorn service.main:app --host 0.0.0.0 --port 8000
.venv/bin/python -m pytest service/tests/   # 47/47 passing
```

Nothing here is stale or half-working — the whole engine layer is finished,
tested, and typechecked. Do not rewrite `engine/` from scratch; extend it.
The renderer (`renderer/`) was built and visually verified step by step per
§4 of the plan — flat tiles → tick loop → folding leaf → fold shadow →
split line → audio — each stage checked in a real browser before moving on.
The service (`service/`) is verified against the renderer end-to-end (Vite
proxies `/current`, `/message`, `/queue`, `/next`, `/compose` to :8000 in
dev) and has its own pytest suite for the files with real logic.

## Architecture decisions already made (don't relitigate these)

- **Cells are integer codes into a fixed flap order**, not characters. The
  array index in `spec/charset.json` *is* the physical flap position.
  63 positions: `0` blank, `1-26` A-Z, `27-36` digits, `37-55` punctuation,
  `56-62` seven color chips.
- **Fixed flap rate, not fixed duration.** `steps = (target - current) mod N`,
  each step takes `flapMs` (~28ms). Duration is never set directly — it's
  emergent from wrap distance. This is *why* the settle cascade looks real
  instead of staggered-by-hand. See `engine/cell.ts`.
- **Engine has zero DOM.** `engine/board.ts` and `engine/cell.ts` know
  nothing about canvas, browsers, or rendering. This is deliberate — it's
  what makes the 25 tests in `engine/__tests__/` runnable in plain Node.
  Keep it that way; the renderer consumes the engine, never the reverse.
- **Charset is one JSON file, two loaders.** `engine/charset.ts` (TS) and
  `python/charset.py` (Python) both load `spec/charset.json` and must agree
  exactly — `python/verify_parity.py` proves it. If you ever touch the
  charset, rerun that script.
- **Retargeting mid-flight redirects from the live position**, not wherever
  the cell started. Covered explicitly in `board.test.ts`
  ("retargeting mid-animation...") — this is the bug class to watch for if
  you touch `cell.ts`.

## What Phase 1B actually built

```
renderer/
  display.html    canvas + kiosk CSS (cursor hidden, no scroll)
  main.ts         wires engine → canvas + audio, poll loop, kiosk hook
  canvas.ts       BoardCanvas: dirty-tile redraw, leaf geometry, fold shading
  audio.ts        BoardAudio: per-flap click scheduling, voice cap
  kiosk.ts        fullscreen-on-first-gesture (cursor hiding is CSS)
  public/
    current.json  static poll target — {"text": "..."} or {"grid": [...]}
vite.config.ts    root: "renderer", npm run dev serves it at :5173
```

- **Dirty-tile redraw is literal**: every frame, redraw exactly the cells
  where `remaining > 0`, plus any cell whose flap event this frame carried
  it to its target (that's the one frame `remaining` is already back to 0).
  See the `frame()` loop in `main.ts`.
- **Leaf geometry matches §4 exactly**: static top half always shows the
  *incoming* code, static bottom half shows *outgoing*; the leaf shows
  outgoing-top for `theta <= 90°`, swaps to incoming-bottom past it,
  `scaleY = |cos(theta)|`. Verified stepwise at phase 0 / 0.5 / 0.999 in a
  real browser (paused single-cell tests) before trusting it live — phase
  0.5 produces the hybrid glyph (incoming-top + outgoing-bottom, leaf
  edge-on and invisible) that's the whole point of the model.
- **No click sample exists on disk.** `audio.ts` synthesizes a ~14ms
  decaying-noise burst into an `AudioBuffer` once at startup instead of
  loading a file. Swap `synthesizeClick()` for a loaded sample later
  without touching the scheduling path. Flaps are scheduled at their
  engine timestamp (not fired synchronously), so flaps crossed within one
  slow tick still land spaced out.
- **`BoardAudio.setGain(0)` is already a hard off-switch**, not a dim —
  satisfies the quiet-hours constraint below. Nothing wires it to a
  schedule yet; that's Phase 2 (`sound_enabled` from the service).
- Poll loop hits real `GET /current` every 5s and checks `charset_version`
  against the renderer's own before applying — a mismatched payload is
  ignored (console warning, not a crash), per §4's "refuse a payload it
  can't correctly display" line. A grid identical to what's already
  showing is a no-op for free — cells already at target produce zero
  flap events.

## What Phase 2 actually built

```
service/
  main.py          FastAPI app: GET /current, POST /message, GET /queue,
                    DELETE /queue/{id}, POST /next, GET /compose
  db.py             SQLite schema (messages, display_log) + connection helper
  selection.py       Selector: pinned wins, else lowest priority, ties to
                    least-recently-shown, holds dwell_seconds before reselecting
  web/compose.html   phone-friendly form, no framework, fetch() POSTs JSON
  requirements.txt / requirements-dev.txt
  flipboard.service  sample systemd unit — untested here (macOS dev box);
                    verify the restart-survives-power-cycle claim on the Pi
  tests/             pytest, 31 tests — see "What Phase 3 actually built"
                    for the compose-engine ones; selection tests use real
                    sqlite3 (:memory:) or a deterministic monkeypatched
                    clock, same "no hidden magic" spirit as the engine's
                    injected-clock tests
```

- **Selection is stateful but simple**: `Selector` holds one in-memory
  `_current` pick. A pinned message preempts an in-progress dwell hold
  immediately (that's what "Pin — show now" in compose.html promises); a
  non-pinned message arriving mid-dwell does not, regardless of its
  priority, until the dwell elapses or `/next` forces it. This was a real
  bug caught by hand-testing with curl before it got fixed — see
  `_pinned_waiting` in `selection.py`.
- **`starts_at`, `expires_at`, and `display_log.shown_at` are all epoch
  floats** — not SQLite's `CURRENT_TIMESTAMP` string format, which only
  has 1-second resolution. `shown_at` used to use that default and it was
  a real bug: rapid reselections (paginated pages cycling via `/next`)
  landed in the same second, tied on the least-recently-shown sort, and
  silently favored the lower id instead of alternating. Caught live with
  curl while testing Phase 3 pagination, fixed by passing `time.time()`
  explicitly on insert — see the regression test in `test_selection.py`
  with a monkeypatched sub-second clock.
- **No auth, CORS, or reverse proxy needed** — the Vite dev server proxies
  API routes to :8000 so the renderer and service are same-origin in dev,
  matching how they'd be served together in production.
- First run seeds one low-priority "FLIPBOARD READY" message so
  `GET /current` never has to special-case an empty board.

## What Phase 3 actually built

```
service/compose/          Replaces Phase 2's service/compose.py wholesale.
  charset.py                Reuses python/charset.py — not a third loader.
  normalize.py               Text -> legal codes: uppercase, drop illegal
                             chars, collapse whitespace runs, emoji -> chip,
                             \n -> NEWLINE sentinel (internal only)
  wrap.py                    Word-wrap over code lists, not strings — a
                             color chip wraps exactly like a letter
  align.py                   Center both axes; floor-division padding
                             gives top/left bias on odd leftover for free
  render.py                  normalize -> wrap -> align, paginates >6 lines
                             into multiple grids instead of truncating
  templates.py               banner / stat / list / countdown / chips
```

- **Operates on code lists end to end, never strings mid-pipeline** — the
  engine's whole "cells are integer codes" philosophy extended into the
  composer. This is what makes chips wrap identically to letters with no
  special-casing.
- **Multi-page overflow needed no schema change.** `service/main.py`'s
  `POST /message` calls `render()` and inserts one `messages` row per
  page (same `raw_text` on each, `dwell_seconds` divided across pages
  with a 20s floor). The existing least-recently-shown tie-break in
  `selection.py` naturally cycles them in order forever — no new
  "which page is next" state needed anywhere.
- **`service/__init__.py` puts `python/` on `sys.path` once**, so every
  submodule under `service/` can `from charset import Charset` without
  repeating the path hack Phase 2's `compose.py` used to do inline.

## What Phase 4 actually built (infrastructure only — see below)

**Scope was deliberately narrowed.** The full phase is 6 channels
(weather, calendar, f1, mufc, markets, milestone) plus a Claude
`/compose/smart` endpoint, and every single one of those needs something
this session doesn't have: a weather API key + location, calendar OAuth,
a football/F1 data source, a stock watchlist, or a personal reference
date for milestone. Asked the user how to scope it; they chose
infrastructure-only. **No channels exist yet** — `CHANNELS` in
`service/channels/__init__.py` is an empty list. What's built is the
machinery that real channels will plug into:

```
service/
  config.py              is_quiet_hours() — placeholder 21:00-07:00 window
                         and brightness floor, needs real tuning
  messages.py             create_message() — extracted from main.py's old
                         inline insert code so POST /message and channels
                         share one pagination/dwell-split path
  channels/
    base.py                Channel (name, cron, run) / ChannelMessage
    __init__.py             CHANNELS registry — empty, ready for weather.py etc.
    scheduler.py            run_channel(): quiet-hours gate, catches a
                          channel's own exceptions so one bad channel
                          can't take down the scheduler. start_scheduler()/
                          stop_scheduler() wired into main.py's FastAPI
                          lifespan (AsyncIOScheduler — needs a running
                          event loop, which is why it's started there and
                          not in a standalone script)
```

- **Quiet hours narrows *selection*, not just the wire fields.**
  `sound_enabled`/`brightness` in `GET /current` already flip correctly,
  but the real behavior is in `selection.py`: `_eligible()` now takes a
  `quiet` flag and excludes every non-pinned message when it's set. This
  means quiet hours interrupts a message that's already mid-dwell the
  *instant* it begins (verified with a test using a toggleable
  monkeypatched flag, not just "starts a new dwell period already
  filtered") — not just for future reselections. A pinned message is the
  only thing that still shows; if nothing's pinned, `GET /current` goes
  blank rather than showing something inappropriate.
- **This surfaced a real test-suite bug, not just app logic.** Every
  existing `test_selection.py` test broke the moment `is_quiet_hours()`
  started being called for real, because it was actually quiet hours
  (past 9pm) when the tests ran and `is_quiet_hours()` reads real
  wall-clock time by default. Fixed with an autouse fixture
  (`not_quiet_hours`) that monkeypatches it to `False` for every test
  except the dedicated quiet-hours ones — the same "don't let wall-clock
  time make tests flaky" discipline the engine's injected-clock tests
  already established, just newly relevant here.
- **`AsyncIOScheduler.start()` requires a running event loop** — a
  standalone `python -c "..."` script can't call it directly; verifying
  the scheduler wiring needed `asyncio.run(...)`, same as it naturally
  gets from uvicorn's loop via the FastAPI lifespan in production.

## Constraints that shouldn't move

- LAN only, no auth — it's a hallway board, not a product.
- SQLite, not Postgres — single-digit writes a day. `service/flipboard.db`
  is gitignored; each environment gets its own.
- IPS/VA target display, never OLED — static grid, burn-in risk.
- Quiet hours matter — there's an infant in the house. Sound and
  brightness both need a hard off-switch, not just a dim setting.
  `BoardAudio.setGain(0)` is that switch on the renderer side;
  `sound_enabled`/`brightness` in `GET /current` (driven by
  `service/config.py`'s `is_quiet_hours()`) is the wire format for it —
  this is now wired end to end, but the window (21:00-07:00) and the
  dim-vs-off choice (currently off, `BRIGHTNESS_QUIET_FLOOR = 0.0`) are
  both placeholders pending the real household schedule and build plan
  probe 6 (never run against actual hardware in this repo).
