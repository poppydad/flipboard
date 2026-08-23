# FlipBoard — Build Plan v2

Self-hosted split-flap message board, built from scratch. ~$180 of hardware and five or six weekends of evenings.

**What changed from v1:** the flipoff fork is gone. The renderer is greenfield, built on flap positions rather than characters, with a headless engine that can be tested without a browser. This costs one extra weekend and buys color chips, correct flap physics, per-flap audio, and a core you can actually assert against.

---

## 0. Design constraints

Decisions, not open questions.

| Constraint | Value | Why |
|---|---|---|
| Grid | 6 rows × 22 cols (132 cells) | Vestaboard's geometry. The constraint is the aesthetic. |
| Cell value | Integer index into a fixed flap order | Matches how the hardware works. Makes animation arithmetic and color chips first-class. |
| Flap rate | Fixed ~28ms per flap, not fixed duration | Settle cascade emerges from wrap distance instead of being faked with staggered delays. |
| Renderer | Canvas 2D, dirty-tile redraw | 400 transforming DOM nodes is where a Pi falls over. |
| Engine | Pure TypeScript state machine, zero DOM | Unit-testable in Node with a deterministic clock. Renderer becomes swappable. |
| Charset | One JSON spec, shared by TS and Python | Two definitions will drift, and the bug will look like "sometimes a letter is wrong." |
| Transport | LAN only, no auth | It's a hallway board. Don't build an identity system. |
| Storage | SQLite | Single-digit writes per day. Postgres here is a costume. |
| Scheduler | APScheduler in-process | One process, one file, systemd keeps it alive. |
| Render loop | Poll `GET /current` every 5s | Websockets are the wrong complexity for a device that changes a few times an hour. |

---

## 1. Architecture

```
flipboard/
  spec/
    charset.json          ← single source of truth, consumed by both sides

  engine/                 TypeScript, no DOM, no browser APIs
    charset.ts            loads spec, code↔char maps
    cell.ts               one cell's flap state machine
    board.ts              132 cells, tick(dt), setTarget(grid)
    events.ts             emits {cellIndex, flapIndex} per flap step
    index.ts              public API

  renderer/               consumes engine state, draws
    canvas.ts             dirty-tile redraw, leaf geometry, fold shading
    audio.ts              per-flap click scheduling, voice cap
    kiosk.ts              poll loop, fullscreen, brightness
    display.html

  service/                Python, FastAPI
    api/                  GET /current, POST /message, GET /queue
    compose/              layout engine — text → 6×22 grid
    channels/             weather, calendar, f1, mufc, markets, milestone
    queue/                priority + dwell selection
    store/                SQLite
    web/                  phone compose form
```

The engine is the asset. Everything else is replaceable around it.

---

## 2. The charset spec

Phase 0 deliverable, because everything downstream depends on it. `spec/charset.json`:

```json
{
  "version": 1,
  "flaps": [
    {"code": 0,  "char": " ",  "type": "blank"},
    {"code": 1,  "char": "A",  "type": "letter"},
    ...
    {"code": 26, "char": "Z",  "type": "letter"},
    {"code": 27, "char": "0",  "type": "digit"},
    ...
    {"code": 36, "char": "9",  "type": "digit"},
    {"code": 37, "char": ".",  "type": "punct"},
    ...
    {"code": 52, "char": null, "type": "chip", "color": "#C0392B"},
    ...
  ],
  "transliterations": {"É": "E", "'": "'", "—": "-", "…": "..."}
}
```

Rules:

- **Order is physical.** The array index *is* the flap position. Reordering it is a breaking change — bump `version`.
- Colors sit at the end, after all printable characters, so a text-only board never wraps through them.
- Total count should be odd-ish and not a power of two; you want wrap distances to feel varied. ~60 flaps is the right neighborhood.
- The TS engine and the Python composer both load this file. Neither hardcodes a single character.

---

## 3. The engine

### Cell state machine

```ts
interface CellState {
  current: number;      // flap index currently showing
  target: number;       // flap index we're heading to
  remaining: number;    // flaps left, = (target - current) mod N
  elapsed: number;      // ms accumulated toward next flap
  phase: number;        // 0..1 through the current flap, for the renderer
}
```

`tick(dt)` accumulates `elapsed`; each time it crosses `FLAP_MS`, decrement `remaining`, advance `current` by one (mod N), emit a flap event. When `remaining` hits zero the cell is settled and stops consuming ticks.

### The animation math

```
steps = (target - current + N) % N
duration = steps * FLAP_MS
```

That's the whole thing. `A → C` is 2 flaps, 56ms. `Z → B` wraps through 30 flaps, 840ms. No stagger constant, no easing curve, no randomness. The cascading settle that makes these boards mesmerizing falls out of the fact that different cells have different distances to travel.

Two tuning knobs and no more:

- `FLAP_MS` — 25 to 35. Feel this on hardware before committing (Phase 0 probe 2).
- `START_JITTER_MS` — 0 to 40ms of random delay before a cell starts. Real boards don't launch in perfect unison. Keep it small; too much and it reads as sloppy rather than mechanical.

### Public API

```ts
const board = new Board(charset, { rows: 6, cols: 22, flapMs: 28 });
board.setTarget(grid);            // 6×22 of codes
board.tick(dt);                   // advance, emits flap events
board.cells;                      // CellState[] for the renderer
board.isSettled;                  // all remaining === 0
board.on('flap', (e) => {...});   // {cellIndex, flapIndex, timestamp}
```

### Tests — the reason for the split

All of these run in Node with an injected clock, no browser:

- `A → C` produces exactly 2 flap events for that cell
- `Z → B` produces exactly 30, not 24 (wrap direction is forward-only, like the hardware)
- A cell whose target equals current produces zero events and never enters the animating set
- Settle order across a full-board change is monotonic in wrap distance
- After `ceil(maxSteps * FLAP_MS / dt)` ticks, `isSettled` is true and `current === target` for all 132
- Total flap events for a known grid transition equals the sum of per-cell wrap distances
- Setting a new target mid-animation retargets from the *current* position, not the old origin

That last one is the bug you'd otherwise ship, and it's invisible without a test.

---

## 4. The renderer

### Canvas over DOM

One canvas, dirty-tile redraw. Each frame, redraw only cells with `remaining > 0`. Settled cells are untouched pixels. A full-board transition is 132 dirty tiles for a moment; a clock update is two.

### Leaf geometry

Each tile draws as two horizontal halves split at the midline:

- **Static top half** — showing the *incoming* character's top portion
- **Static bottom half** — showing the *outgoing* character's bottom portion
- **Folding leaf** — the outgoing character's top half, rotating down through 0→90°, then the incoming character's bottom half continuing 90→180°

Vertical squash approximates the perspective: `scaleY = |cos(θ)|`. At the halfway point the leaf is edge-on and invisible, which is where you swap which face is drawn.

Three details that do most of the work:

1. **Fold shadow** — a linear gradient darkening the leaf as it approaches horizontal, plus a cast shadow on the half beneath it. This is what reads as 3D. Trivial in canvas, painful in CSS.
2. **Split line** — a 1–2px dark gap at the midline, always visible, even on settled tiles. Without it the board looks like a font, not a mechanism.
3. **Tile gap and inset** — cells sit in recessed wells with a subtle inner shadow. The board's texture comes from the gaps as much as the tiles.

### Audio

Per-flap, not per-message. This is the single biggest realism difference from every web split-flap you've seen.

- One short click sample (10–20ms), loaded once into an `AudioBuffer`
- Every flap event schedules a `BufferSource` at its exact timestamp
- Jitter gain ±15% and `playbackRate` ±5% per voice so it doesn't sound like a machine gun
- **Voice cap ~24 concurrent** — beyond that, drop rather than play. A full-board transition fires 132 near-simultaneous flaps and uncapped it clips into white noise
- Master gain from the server's `sound_enabled` / quiet-hours state

The clatter density then tracks the animation for free: a small change ticks, a full change roars and tapers.

---

## 5. Bill of materials

| Item | Est. | Notes |
|---|---|---|
| Used 24–27" IPS monitor | $50–70 | FB Marketplace. **IPS or VA only — never OLED.** Static grid burns in. |
| Raspberry Pi 5 (4GB) + PSU + SD | $85 | Pi 4 works if you already have one. |
| Matte anti-glare film | $12 | Kills the "screen" tell more than anything else here. |
| Poplar 1×3 + black felt | $20 | Deep frame, felt-lined, panel recessed. |
| French cleat + hardware | $10 | |
| **Total** | **~$180** | |

Fallback for software validation: any old tablet in kiosk mode. $0, and enough to run Phases 1–3.

---

## 6. Phase 0 — probes

Each is throwaway. Answer, record, delete. Nothing starts until all six are green.

1. **Charset spec drafted.** Write `charset.json`, load it from both a TS file and a Python file, assert both produce identical code→char maps. *Deliverable, not a probe — but it gates everything.*
2. **Flap rate feel.** Hardcode a single animating tile at 20 / 28 / 35ms and watch each for a minute. *Pick `FLAP_MS` by eye before building anything around it.*
3. **Canvas perf on Pi.** 132 tiles, full-board transition, on the actual Pi at target resolution. Frame time during the worst moment. *If this fails, the fallback is fewer simultaneous animating cells — stagger targets in waves — not a different renderer.*
4. **Audio under load.** 132 flap events in a 900ms window with the voice cap on. Does it clatter or clip? *Tune the cap here, once.*
5. **Legibility at distance.** Static 6×22 grid, viewed from where the board will hang. Does 22 columns read at 8 feet? *If no, the geometry changes — find out before the engine exists.*
6. **Night brightness floor.** Dimmest readable setting. Is it still too bright for a dark hallway at 3am? *Decides whether quiet hours means dim or fully off.*
7. **Claude grid quality.** One manual API call: a day's calendar → a 6×22 grid under the charset rules. *Decides whether §10 is a feature or a deleted section.*

---

## 7. Phase 1A — engine (weekend 1)

Pure TypeScript, Node only, no browser opened at any point.

- `charset.ts` loads and validates the spec
- `cell.ts`, `board.ts`, `events.ts` per §3
- Full test suite from §3, running in Vitest
- A CLI harness: `npm run sim -- "HELLO" "WORLD"` prints per-cell flap counts and total duration to stdout

**Done when:** every test in §3 passes and the CLI reports correct wrap distances for hand-checked cases. You have not drawn a single pixel.

---

## 8. Phase 1B — renderer (weekend 2)

- Canvas tile drawing per §4, starting with flat two-tone tiles and no animation
- Add the folding leaf, then the fold shadow, then the split line — in that order, checking each
- Wire to the engine's tick loop via `requestAnimationFrame`
- Audio last, once the visuals are right
- Poll loop against a static JSON file; no backend yet
- Chromium kiosk autostart, screen blanking off, cursor hidden

**Done when:** it survives a power cycle, comes back up on its own showing the board, no keyboard attached.

---

## 9. Phase 2 — service and phone posting (weekend 3)

**Schema**

```sql
CREATE TABLE messages (
  id            INTEGER PRIMARY KEY,
  source        TEXT NOT NULL,      -- 'manual' | channel name
  raw_text      TEXT,               -- for re-render on charset bump
  grid          TEXT NOT NULL,      -- JSON 6×22 of codes
  priority      INTEGER DEFAULT 50, -- 0 highest
  dwell_seconds INTEGER DEFAULT 300,
  starts_at     TIMESTAMP,
  expires_at    TIMESTAMP,
  pinned        BOOLEAN DEFAULT 0,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE display_log (
  id INTEGER PRIMARY KEY,
  message_id INTEGER REFERENCES messages(id),
  shown_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**API**

| Method | Path | Notes |
|---|---|---|
| `GET` | `/current` | `{id, cells, charset_version, sound_enabled, brightness}` |
| `POST` | `/message` | `{text, priority?, dwell?, expires_at?, pinned?}` |
| `GET` | `/queue` | Upcoming, in order |
| `DELETE` | `/queue/{id}` | |
| `POST` | `/next` | Force advance |
| `GET` | `/compose` | Phone-friendly form, no framework |

`charset_version` in `/current` lets the renderer refuse a payload it can't correctly display rather than showing wrong letters.

**Selection** — one deterministic function: pinned wins; else lowest priority among non-expired and `starts_at`-eligible; ties to least-recently-shown. Hold `dwell_seconds`, reselect.

**iOS Shortcut:** "Post to Board" → Ask for Text → POST. Home screen. This is ninety percent of how you'll use it.

**Done when:** phone → board works from the couch and the service restarts cleanly under systemd.

---

## 10. Phase 3 — layout engine (weekend 4)

Python, pure functions, no I/O. Build with a browser preview harness so you can eyeball a hundred inputs fast.

```
compose/
  charset.py    loads spec/charset.json
  normalize.py  text → legal codes
  wrap.py       word wrapping within 22 cols
  align.py      horizontal + vertical placement
  render.py     orchestration → 6×22
  templates.py  named layouts
```

**Normalize:** uppercase; apply spec transliterations; emoji → nearest color chip where one maps, else drop; anything still illegal is dropped, never a placeholder box.

**Wrap:** never break mid-word unless the word exceeds 22 chars (then hard-break, no hyphen); collapse whitespace runs; honor explicit `\n`; content over 6 lines splits into sequential linked grids with shorter dwell — never truncate silently.

**Align:** default centered both axes. Odd leftover space biases top and left. Pick one bias and never vary it; inconsistency is what makes a board look cheap.

**Templates:** `banner` (one line, rows 3–4), `stat` (label / value / context), `list` (header + 4 items), `countdown` (label / number / unit), `chips` (color border framing text).

**Tests:** every code round-trips; 22-char word fits exactly; 23-char hard-breaks; empty string → blank grid, no crash; 500-char paragraph → N grids, zero lost words; every template output is exactly 6×22 with only legal codes.

---

## 11. Phase 4 — channels and Claude

| Channel | Schedule | Template |
|---|---|---|
| `weather` | 6:30am, 4:00pm | `stat` |
| `calendar` | 7:00am | `list`, max 4 |
| `f1` | race weekends | `countdown` to lights out, results Sunday |
| `mufc` | match days | `countdown` pre-match, score after |
| `markets` | 4:15pm weekdays | `list` — watchlist movers |
| `milestone` | 8:00am | `banner` — days-old counter |
| `manual` | on demand | whatever you typed |

**Claude composition** (only if probe 7 was green): `POST /compose/smart {text}`. System prompt states geometry, legal charset, and template names; demands JSON `{template, lines[]}` — never raw cell codes. The layout engine owns geometry; Claude only decides what to say and how to shape it. Validate against the engine, fall back to `banner` on anything malformed.

**Quiet hours** — non-negotiable in this house. Sound off unconditionally, brightness to floor or panel off per probe 6, no channel pushes, pinned manual messages only. Wakes at `quiet_end` with the morning set.

---

## 12. Phase 5 — enclosure

Last. A working board on a shelf beats a beautiful frame around unfinished software.

Deep poplar frame, black-stained, felt-lined, panel recessed ~1cm. Recess plus matte film is what stops it reading as a monitor. Cable exit through the bottom rail. French cleat. Pi on the VESA mount behind the frame.

---

## 13. Risks

| Risk | Mitigation |
|---|---|
| Burn-in | IPS/VA only. Quiet-hours blanking. Rotate content. |
| Canvas perf on Pi | Probe 3. Fallback is staggering targets into waves, not changing renderer. |
| Audio clipping on full-board changes | Probe 4 sets the voice cap. Drop voices, don't mix them. |
| Charset drift between TS and Python | One JSON file, version field in `/current`, renderer refuses mismatched payloads. |
| Leaf animation looks like a font, not a mechanism | Split line and fold shadow are not polish — build them in Phase 1B, not later. |
| Greenfield scope creep | The engine is 6 rows × 22 cols of one board. No themes, no plugins, no configurable geometry beyond rows/cols. |
| Weekend estimates optimistic with an infant | They are. Phases 1A/1B and 2 are independently useful. Stop after Phase 2 and you still have a board worth having. |

---

## 14. Sequence

```
Phase 0   probes + charset spec    evening    7 answers, 1 spec file
Phase 1A  engine                   weekend    tested state machine, zero pixels
Phase 1B  renderer                 weekend    it looks and sounds right
Phase 2   service + phone          weekend    phone → board round trip
Phase 3   layout engine            weekend    arbitrary text → clean grid
Phase 4   channels + Claude        weekend    it tells you things unprompted
Phase 5   enclosure                weekend    it stops looking like a monitor
```

Minimum viable stopping point is end of Phase 2. Everything after is upside.
