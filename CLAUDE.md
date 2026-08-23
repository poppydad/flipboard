# flipboard — project context

Self-hosted split-flap message board, replacing a $3,400 Vestaboard. Full
plan is in `flipboard-build-plan-v2.md` at the repo root — read that first,
it has the phase breakdown, the bill of materials, and the risk table.

## Where things stand

**Phase 0 (charset spec), Phase 1A (headless engine), and Phase 1B (canvas
renderer) are done and green.**

```
npm install
npm test                          # 25/25 passing
npm run sim -- "HELLO WORLD"      # CLI sim: flap counts + settle time
python3 python/verify_parity.py   # TS/Python charset agreement check
npm run typecheck                 # engine + cli + renderer, clean
npm run dev                       # Vite dev server, open /display.html
```

Nothing here is stale or half-working — the whole engine layer is finished,
tested, and typechecked. Do not rewrite `engine/` from scratch; extend it.
The renderer (`renderer/`) was built and visually verified step by step per
§4 of the plan — flat tiles → tick loop → folding leaf → fold shadow →
split line → audio — each stage checked in a real browser before moving on.

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
- Poll loop hits `/current.json` (Vite's `renderer/public/`) every 5s,
  same shape `GET /current` will return in Phase 2 (`{text}` or `{grid}`).
  A grid identical to what's already showing is a no-op for free — cells
  already at target produce zero flap events.

## Constraints that shouldn't move

- LAN only, no auth — it's a hallway board, not a product.
- SQLite, not Postgres — single-digit writes a day (this matters for Phase 2,
  not yet relevant to the renderer).
- IPS/VA target display, never OLED — static grid, burn-in risk.
- Quiet hours matter — there's an infant in the house. Sound and brightness
  both need a hard off-switch, not just a dim setting. Not renderer work yet,
  but keep the audio engine's gain control easy to zero out from outside.
