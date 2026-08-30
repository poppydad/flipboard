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
.venv/bin/python -m pytest service/tests/   # 192/192 passing
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
  selection.py       Selector: pinned wins, else round-robin by
                    least-recently-shown (priority breaks ties, it does NOT
                    outrank — see the monopoly bug below), holds
                    dwell_seconds before reselecting
  web/compose.html   phone-friendly form, no framework, fetch() POSTs JSON
  requirements.txt / requirements-dev.txt
  tests/             pytest, 65 tests — see "What Phase 3 actually built"
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
- **`idx_display_log_message_id` is load-bearing, not decoration.**
  `selection.py`'s `_pick` and `_pinned_waiting` both correlate every
  message against `MAX(shown_at)` for that message. Unindexed that's
  O(messages x log rows): measured 1.5s per `GET /current` at three
  months of real traffic and 24.8s at one year, against a renderer that
  polls every 5s. With the index the same year's data selects in 34ms
  and five years in 188ms — which is also why there's no row reaper.
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

- **`normalize()` walks codepoints, so emoji keys must be single
  codepoints.** Phones append U+FE0F (the variation selector) to
  characters with both a text and an emoji presentation, so `"❤️"`
  arrives as two codepoints and a two-codepoint dict key can never
  match — the chip was silently dropped. `_VARIATION_SELECTOR` is now
  skipped in the loop and `test_emoji_table_keys_are_single_codepoints`
  guards the table against the same mistake.
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

## What Phase 4 actually built (infrastructure + 3 of 6 channels)

**Scope was deliberately narrowed.** The full phase is 6 channels
(weather, calendar, f1, mufc, markets, milestone) plus a Claude
`/compose/smart` endpoint. calendar, mufc, and markets each need
something this session doesn't have: calendar OAuth/an ICS feed URL, a
football data API key, a stock watchlist. Asked the user how to scope
it; they chose infrastructure-only, then supplied what the other three
needed as the conversation went on — a reference date for milestone
(2025-11-08), coordinates for weather (40.304251, -74.776508), and f1
needed nothing at all (OpenF1 is free/keyless) — so all three got built.

```
service/
  config.py              is_quiet_hours() — real household window
                         (20:00-07:00); brightness floor still placeholder
  messages.py             create_message() — extracted from main.py's old
                         inline insert code so POST /message and channels
                         share one pagination/dwell-split path
  channels/
    base.py                Channel (name, cron, run) / ChannelMessage
    __init__.py             CHANNELS registry: [milestone, weather, f1]
    http.py                 get_json(): shared fetch helper, pins certifi's
                          CA bundle explicitly (see note below)
    milestone.py            days = today - REFERENCE_DATE, via banner,
                          8:00am daily — no external API
    weather.py               Open-Meteo (free, keyless), via stat,
                          6:30am + 4:00pm
    f1.py                    OpenF1 (free, keyless), via countdown/list,
                          hourly poll that decides for itself whether
                          there's a countdown or results worth posting
    scheduler.py            run_channel(): quiet-hours gate, _supersede(),
                          catches a channel's own exceptions so one bad
                          channel can't take down the scheduler. start_scheduler()/
                          stop_scheduler() wired into main.py's FastAPI
                          lifespan (AsyncIOScheduler — needs a running
                          event loop, which is why it's started there and
                          not in a standalone script)
```

- **A channel's new message supersedes its own previous one**
  (`scheduler.py`'s `_supersede`). A cron firing is a *poll*, not
  necessarily news: f1 polls hourly but its countdown only changes ~37
  times in the 14 days before a race, so 89% of its posts were exact
  duplicates. Every one used to leave a permanent row, and because
  `_pick` ties every never-shown row at `last_shown = -1.0` and sorts
  stably, the **lowest id — the stalest countdown — won every time**. A
  board counting down to a race sat on "14 DAYS" for two hours and took
  28 hours to drain 336 rows, while manual messages (priority 50) queued
  behind f1's 15. The `UPDATE` is scoped by `source`, so `POST /message`
  is untouched, and runs in the same transaction as the insert that
  follows, so a channel is never left with its old message expired and
  no new one in place. Note this removes the *backlog*, not the priority
  ordering: one live f1 message still legitimately preempts a manual one,
  which is §9's documented rule, not a bug.
- **`service/channels/http.py` pins certifi's CA bundle explicitly**
  rather than trusting the host Python's default SSL config. Found this
  the hard way: weather.py's first live test failed with
  `CERTIFICATE_VERIFY_FAILED` even though `curl` hit the exact same URL
  fine — this dev machine's python.org-installed Python isn't wired to
  the macOS system keychain the way `curl` is. Explicit certifi avoids
  depending on that being configured right on whatever machine (dev
  laptop, Pi) ends up running this.
- **f1.py wraps "now" behind a `_now()` function** instead of calling
  `datetime.now(timezone.utc)` directly, specifically so tests can
  monkeypatch it — `datetime` is an immutable C type, so `datetime.now`
  itself can't be patched in place the way `time.time` can. Verified
  live against the real OpenF1 API before writing the mocked tests: it
  correctly found an actual upcoming race and displayed the right
  countdown.
- **All three channels verified against the live server's real sqlite
  file, not just `:memory:` unit tests** — simulated their triggers by
  calling `run_channel()` directly with `is_quiet_hours` patched to
  `False`, confirmed each row's `source`/priority, decoded the stored
  grid back to readable text, and for f1 specifically, watched the
  result render correctly on the actual canvas in a browser (temporarily
  pinning it, since it was genuinely quiet hours during testing).

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

## `POST /compose/smart` — free heuristic version, not the Claude one

The plan's §11 gates `/compose/smart` on Claude actually deciding
template/shape, behind "probe 7 was green" — probe 7 was never run
(it's a paid API call), and there's still no `ANTHROPIC_API_KEY` in
this environment. The user chose the free path now, Claude-backed later
if the key ever gets set up: `service/compose/smart.py`'s `pick(text)`
recognizes a handful of text shapes by regex and maps them straight
onto the existing templates, no network call:

- `"5 days until vacation"` / `"trash pickup in 2 days"` → `countdown`
- `"Outside: 72F, feels chilly"` (colon, <3 comma items) → `stat`
- `"Groceries: milk, eggs, bread"` (colon, ≥3 comma items) → `list`
- multi-line text (header line + item lines) → `list`
- anything else → `None`

`pick()` also returns `None` when a matched shape *wouldn't fit* —
`smart.py`'s `_fits()` checks each field against one line, and rejects
lists over 4 items. Templates place each field on a fixed row via
`templates._one_line`, which keeps `lines[0]` and silently drops the
rest; that's fine for the short structured values channels feed it, but
`pick()` feeds it whatever a person typed. Without the check,
`"Reminder: pick up the dry cleaning before six today"` rendered as
`"REMINDER / PICK UP THE DRY"` and lost the rest — worse than plain
`POST /message`, which this endpoint promises never to be.

`None` isn't a failure — `POST /compose/smart` in `service/main.py`
falls straight through to the normal `create_message(text=...)` path
(the same one `POST /message` already uses) whenever nothing matches,
so this endpoint is never worse than plain `/message`, only sometimes
better. 12 new tests in `service/tests/test_smart.py`, covering both
the matches and the "why didn't this match" edge cases (label too long,
single line with no colon, digit-led text that isn't actually a
countdown). Live-verified end to end: posted all four shapes through
the running service, decoded the stored grids back to text to confirm
correct centering/wrapping, confirmed `/current` correctly selected the
countdown message, and watched `"VACATION / 5 / DAYS"` render correctly
on the actual canvas in the browser.

If the user later sets up `ANTHROPIC_API_KEY`, the plan is to add a
second picker (an actual Claude call, validated against the engine,
falling back to `banner` per §11) and let `/compose/smart` try that
first, falling back to this heuristic version, not replace it — the
heuristic path costs nothing and needs no network, so it's worth
keeping as the fallback rather than deleting once Claude is wired in.

## Live scores take the whole board

mufc and f1 poll every five minutes (`*/5`), and while a match or race is
actually running they post a **pinned** message — which is what "don't
display anything else for the duration" means in this codebase, since
`selection.py` already gives pinned exclusive hold.

- **The live match is invisible to the endpoint that lists results.**
  ESPN's bare team schedule only returns finished matches; a game in
  progress appears only under `?fixture=true`, with `status.type.state ==
  "in"` and a running clock. Using the per-league `scoreboard` endpoint
  instead would have worked but would miss cup competitions.
- **OpenF1's `/position` is a log of position changes, not a standings
  snapshot.** `_live_message` filters to `position<=3` and keeps the most
  recent record per place — the last time anyone took P1 is who holds P1.
- **Live messages expire in 15 minutes** while being re-confirmed every 5.
  A pinned message that outlived the feed going quiet would hold the board
  indefinitely, which is the exact failure mode the f1 countdown already
  demonstrated once.
- **`scheduler._refresh_if_unchanged` is what makes 5-minute polling
  survivable.** A scoreline sits unchanged for most of a match, so an
  identical poll bumps the existing row's expiry instead of superseding
  and re-inserting. Without it every cycle writes a new row whose
  `last_shown` is never-shown, which distorts the round-robin — and it
  also finally fixes the 89%-duplicate problem the f1 countdown had at
  hourly polling.

## Every channel message expires

Reported from the room: the board read 82F on a 21C night. The data was
never wrong — Open-Meteo had 69.5F at that moment — the *message* was seven
hours old. weather posted at 16:30 with no `expires_at` and stayed eligible
all evening.

`scheduler.py`'s `_supersede` only retires a channel's previous message
when a new one lands. It cannot help when the channel doesn't run again,
which is every night (quiet hours gates it) and any time an API is down.
So expiry has to come from the message itself:

- `base.expires_in(hours)` / `base.expires_at_midnight()` — use one or the
  other in every channel.
- weather 4h, and its cron went from twice a day to every three hours
  (`15 7,10,13,16,19`). Twice a day was always going to show an afternoon
  reading at bedtime.
- f1/mufc 3h (they poll hourly, so this rides out a couple of failures).
- milestone and holiday: midnight, since both are about *today*.

Pick a span longer than the polling interval and shorter than the time it
would take to become a lie.

## Sound needed two unrelated fixes

Reported as "there is no sound". Neither cause was in the audio code —
`audio.ts` had been synthesising clicks correctly the whole time.

- **PipeWire had no HDMI sink at all**, only a `Dummy Output`. The Pi 5's
  `vc4-hdmi` ALSA device advertises exactly one format,
  `IEC958_SUBFRAME_LE` (raw S/PDIF framing), so `hw:1,0` rejects ordinary
  PCM with "Setting of hwparams failed" — `plughw:1,0` works because it
  converts. WirePlumber wasn't applying ACP to the card, so it found
  nothing usable and fell back. `deploy/hdmi-audio.conf` forces
  `api.alsa.use-acp`, which produces the normal "Digital Stereo (HDMI)"
  profile. Installed by `install.sh`; without it a rebuilt Pi is silent
  again.
- **Chromium never started the AudioContext.** Web Audio begins suspended
  and resumes on the first user gesture; `main.ts` listens for
  `pointerdown`/`keydown` to do that. On a wall panel nobody ever clicks,
  so it stayed suspended forever. `--autoplay-policy=no-user-gesture-required`
  in `kiosk.sh` is the fix. The tell is `wpctl status`: before, Chromium
  appeared only as an *input* client; with audio actually running it shows
  output clients too.
- The monitor does have speakers — `/proc/asound/card1/eld#0.0` reports
  `speakers [0x1] FL/FR` and an LPCM SAD. Check that file before assuming
  a panel can't play sound.

## Brightness: three layers, only two of them reachable

- **Image brightness/contrast** — a CSS filter on the canvas
  (`BoardCanvas.setBrightness`/`setContrast`), set from the phone form via
  `POST /settings/display` and persisted in the `settings` table. This is
  the only knob that reaches the *pixels*.
- **Panel power** — `deploy/panel.sh` polls `GET /current`'s `brightness`
  and runs `wlopm --off/--on`. It follows that field rather than
  reimplementing the schedule, so the phone form's snooze and
  `FLIPBOARD_QUIET_HOURS` come along for free. `ExecStopPost` turns the
  panel back on, so stopping the unit can never strand a dark board.
- **The monitor's own backlight** — **not reachable.** `ddcutil` reads the
  ARZOPA's EDID fine but gets nothing at I2C 0x37: the panel doesn't
  implement DDC/CI, and no HDMI monitor exposes `/sys/class/backlight`.
  This is why "brightness 0" alone isn't darkness — a black LCD is still a
  lit LCD — and why the panel gets powered off outright during quiet
  hours. That answers build plan probe 6 for *this* monitor: off, not dim,
  because dim isn't available.

## The holiday channel and `compose/art.py`

Thirteen festivals, each with a greeting and chip art, on the day —
Hindu, plus both Eids and Christmas.

- **The festival dates are a baked-in table, not a fetch.** They're
  lunar, so they can't be computed, but they're published years ahead —
  and the one morning this channel matters is exactly the morning you
  don't want a network hiccup to eat. The table came from Google's public
  Indian-holidays iCal feed (free, keyless) and covers 2026–2031;
  `holiday.py`'s docstring says how to regenerate it. **After 2031 the
  channel goes quiet with no error** — `test_the_table_has_not_silently_run_out`
  is the tripwire.
- **The Eid dates are approximate.** They depend on an actual moon
  sighting, which is why the feed marks future ones "(tentative)"; the
  observed day can land either side of the table. Both Eids share one
  crescent-and-star grid and one greeting.
- **Art is written as literal rows of palette keys**, one character per
  cell, so the source looks like the output:
  `"..OOO..OOO..OOO..OOO.."`. A grid built by index arithmetic can't be
  reviewed by reading it. `from_rows` is strict about row count and width
  precisely because a row one character short would shift everything
  below it and look like a renderer bug rather than a typo.
- **Symbols, not figures.** A diya, a thread, a trident, a modak — not
  deities. 132 flat cells can't render a figure without it looking crude,
  and these are religious festivals.
- **`caption()` clears its row before writing** rather than compositing,
  so the greeting always sits on unlit cells no matter how busy the art
  is around it.
- **These messages set `expires_at` (midnight)** — the only channel that
  does. Worth copying: channel messages that never expire are what let
  f1's countdown sit on the board for a week.

## mufc: ESPN's public API, no key after all

The build plan blocked this channel on a football-data.org key. It needs
nothing — `site.api.espn.com` is free and keyless, like Open-Meteo and
OpenF1 before it. Worth checking for the remaining channels too before
asking for credentials.

- **Two endpoints, not one.** The bare team schedule returns matches
  *already played*; `?fixture=true` returns the ones to come. Neither
  gives both, which is why `_events(fixtures=)` exists.
- **Scores come back as `{"value": 2.0, "displayValue": "2"}`.**
  `_score()` returns an `int`, deliberately: comparing the display
  strings makes `"10" > "9"` False (a 10-9 win would have printed LOST),
  and `str(2.0)` would have put "2.0" on the board.
- **`countdown_parts()` in `base.py` is shared with f1** and exists
  because both printed "1 DAYS". The unit gets a whole 22-column row, so
  the plural is not cosmetic. Floors to the largest whole unit, matching
  f1's existing convention.
- **The fixture line names both sides** — "MUFC VS IPSWICH", not
  "VS IPSWICH", which reads like half a sentence. VS/AT still carries
  home or away. A long opponent that would push past 22 columns drops
  *our* name rather than truncating theirs mid-word.
- Team id 360 under `eng.1`; the team schedule spans every competition,
  not just the league. `_US` matches on ESPN's `shortDisplayName`
  ("Man United") — if that string ever changes, `_parse` returns None and
  the channel goes quiet rather than posting something wrong.

## Selection rotates; priority is a tie-break, not a ranking

Found on the live board. `_pick` used to sort by `(priority, last_shown)`,
so the lowest priority number won every reselection for as long as it
stayed eligible. f1 posts a countdown at priority 15 with no `expires_at`,
so "LIGHTS OUT / 10 DAYS" owned the display and weather (25), milestone
(30) and every phone message (50) were invisible — for the ten days until
the race. `POST /next` returned the same id every time; the queue was full
and nothing moved.

Now `(last_shown, priority)`. Everything gets airtime; priority still
orders messages that are equally stale, which in practice means the
never-shown ones, so a fresh channel post still lands ahead of an older
manual message. Preempting everything *now* is what `pinned` is for, and
that path is untouched. Regression test:
`test_high_priority_message_does_not_monopolize_the_board`.

Note this supersedes the older claim in the Phase 4 notes that "one live
f1 message still legitimately preempts a manual one" — true of the
original design, and the reason the board sat on one grid for a day.

## Running on the real Pi (`deploy/`)

Hardware arrived 2026-08-26: Pi 5 (4GB), Debian 13 trixie, labwc/Wayland,
lightdm autologin to `abprad`. Everything below was set up and verified on
that machine, not imagined — screenshots off the Pi's own framebuffer via
`grim`, not a laptop browser.

```
deploy/
  install.sh         build + install unit + wire autostart; no root, idempotent
  flipboard.service  systemd --user unit
  kiosk.sh           labwc autostart hook: waits for :8000, then Chromium --kiosk
```

- **Production serves the built bundle from FastAPI — the Vite dev server
  is not part of the deployed system.** `npm run build` emits `dist/`
  (13KB), and `service/main.py` mounts `/assets` plus serves
  `dist/display.html` at `/` and `/display.html`. That collapses two
  processes into one, drops the dev-only API proxy (same origin for real
  now, not simulated), and means the board doesn't depend on a dev server
  staying alive. The mount is guarded by `DIST_DIR.is_dir()` so a laptop
  that has only ever run `npm run dev` still starts.
- **It's a `systemctl --user` unit, not a system one.** Installing to
  `/etc/systemd/system` needs root, and `sudo` on this Pi is
  password-prompting (an earlier apparently-passwordless `sudo` was a
  cached timestamp from something typed at the desktop — don't be fooled
  by that again). A user unit needs no root, and since Pi OS autologins to
  the desktop session that the kiosk browser has to live in anyway, tying
  the service's lifetime to that session is correct rather than a
  compromise. `WantedBy=default.target`.
- **`deploy/kiosk.sh` exists because three things bite otherwise**, all
  found live: systemd starts the service and labwc concurrently, so
  Chromium can reach the port before uvicorn binds it and then sit on an
  error page forever (hence the wait-for-`/current` loop); swayidle blanks
  the panel after a few minutes, which for a hallway board is a failure
  (hence `pkill -x swayidle` + `wlopm --on`); and reusing the everyday
  Chromium profile means a crash-restore bubble can land on the board
  (hence a dedicated `--user-data-dir`).
- **The phone form can snooze quiet hours, but only until morning.**
  `POST /settings/quiet-hours {"snooze": true}` suppresses it until the
  next `QUIET_HOURS_END` (07:00) and then lets it resume by itself;
  there is deliberately no indefinite off-switch in the UI. The form is
  the one place a half-asleep person will tap this, and a board left
  bright all night is the exact failure quiet hours exists to prevent —
  so the snooze targets a wall-clock time, not a duration. It lives in a
  new `settings` table read through `service/settings.py`, which caches
  in a module global because `is_quiet_hours()` runs on every
  `GET /current`, i.e. every 5s per renderer; that cache leaks across
  tests, hence the restoring fixture in `test_settings.py`.
- **`FLIPBOARD_QUIET_HOURS=off` disables quiet hours entirely**
  (`service/config.py`, read once at import). This exists because the
  first live test happened at 9pm and the board was — correctly —
  completely black, which is indistinguishable from "broken" when you're
  standing in front of it. Editing `QUIET_HOURS_START` to fake daytime
  works but is a code change you must remember to revert; a systemd
  drop-in at
  `~/.config/systemd/user/flipboard.service.d/quiet-hours-off.conf` is one
  file to delete. **There is currently such a drop-in on the Pi** — remove
  it and `systemctl --user daemon-reload && systemctl --user restart
  flipboard` to restore the real 20:00–07:00 window.
- **Debugging gotcha that cost real time**: a manually-started uvicorn left
  over from earlier testing held :8000, so the systemd unit failed to bind
  and sat in `activating` with a climbing restart counter, while `curl
  /current` cheerfully answered — from the *old* process running *old*
  code. Symptoms were "the env override does nothing" and "the new static
  route 404s". `ss -lptn 'sport = :8000'` names the actual PID; check that
  before believing anything else.
- **Phones should use `http://raspberrypi.local:8000/compose`**, not the
  IP — mDNS, so it survives a DHCP change. `compose.html` carries
  `apple-mobile-web-app-*` meta tags and `/icon.png` (a 478-byte PNG
  generated by hand — no image library on the Pi, and a screenshot icon
  looks terrible), so "Add to Home Screen" gives a chrome-less one-tap app
  rather than a bookmark.

## Constraints that shouldn't move

- LAN only, no auth — it's a hallway board, not a product.
- SQLite, not Postgres — but note the write rate is no longer
  single-digit: three channels on cron put ~27 rows/day in `messages` and
  ~288/day in `display_log`. That's still trivially within SQLite, but it
  is what makes `idx_display_log_message_id` load-bearing rather than
  decorative (see below). `service/flipboard.db` is gitignored; each
  environment gets its own.
- IPS/VA target display, never OLED — static grid, burn-in risk.
- Quiet hours matter — there's an infant in the house. Sound and
  brightness both need a hard off-switch, not just a dim setting.
  `BoardAudio.setGain(0)` and `BoardCanvas.setBrightness(0)` are those
  switches on the renderer side; `sound_enabled`/`brightness` in
  `GET /current` (driven by `service/config.py`'s `is_quiet_hours()`) is
  the wire format for both. Verified end to end in a real browser during
  live quiet hours: the service sends `brightness: 0.0` and the canvas'
  computed filter becomes `brightness(0)`. Brightness was declared on
  the payload interface but never applied for a while — sound was wired,
  brightness was dead on arrival — so if you touch `poll()` in
  `renderer/main.ts`, check both, not just the one that makes noise.
  The window is the household's real schedule (20:00-07:00, tuned
  2026-08-23). The dim-vs-off choice is
  still a placeholder (currently off, `BRIGHTNESS_QUIET_FLOOR = 0.0`) —
  that one needs build plan probe 6, never run against actual hardware
  in this repo.
