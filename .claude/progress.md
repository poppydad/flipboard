# flipboard — running progress log

Kept on disk (not just chat history) so work is recoverable after a
dropped connection. Updated as milestones land, most recent first.
See `flipboard-build-plan-v2.md` for the phase plan and `CLAUDE.md` for
architecture decisions already made.

## Status

- **Phase 0, 1A, 1B, 2**: done, green, pushed to `main` on
  github.com/poppydad/flipboard (commits `9af6c39`, `93fa65c`).
- **Phase 3 (layout engine)**: built, tested, verified live — not yet
  committed/pushed. Docs (CLAUDE.md, README) not yet updated for it either.

## Log

- 2026-08-22 23:xx — Found and fixed a real latent bug while live-testing
  pagination: `display_log.shown_at` defaulted to SQLite's
  `CURRENT_TIMESTAMP`, which only has 1-second resolution. Rapid forced
  reselections (e.g. a paginated message's pages cycling via `/next`)
  landed in the same second, tied, and silently fell back to row order —
  always favoring the lower id, so pages could get stuck instead of
  alternating. Fixed by making `shown_at` an explicit Python epoch float
  (`time.time()`), same representation as `starts_at`/`expires_at`.
  Reproduced live with curl (stuck on id 2 after id 3 once), confirmed
  fixed live (clean 2,3,2,3,2,3 alternation), and added a regression test
  with a monkeypatched sub-second clock. All 31 pytest + 25 TS tests +
  typecheck + charset parity green. Verified visually in the browser too
  (a real paginated page rendering correctly on the canvas).
- 2026-08-22 23:xx — Phase 3 engine built and tested:
  `service/compose/` package (charset, normalize, wrap, align, render,
  templates) replacing `service/compose.py` wholesale. Operates on code
  lists throughout (not strings) so a color chip wraps exactly like a
  letter. `service/main.py` and `service/db.py` updated to use `render()`;
  a message that overflows 6 rows now inserts one DB row per page with
  `dwell_seconds` divided across pages (floor 20s) — reuses the existing
  least-recently-shown tie-break to cycle pages in order, no schema
  change needed. `service/tests/` at 30/30 passing (21 new: 16 compose-
  engine + fixed 2 leftover Phase 2 test bugs found along the way, plus
  the existing 9 selection tests). Next: live end-to-end check in the
  browser (multi-page cycling on the actual renderer), then commit + push
  if it holds up.
- 2026-08-22 23:xx — Starting Phase 3: layout engine (`service/compose/`
  package replacing `service/compose.py` wholesale, per plan §10).
  Plan: `normalize.py` (text → legal codes, emoji → chip), `wrap.py`
  (word-wrap over code lists, not strings), `align.py` (center + top/left
  bias on odd leftover), `render.py` (orchestrates + paginates >6 lines
  into multiple linked grids), `templates.py` (banner/stat/list/countdown/
  chips). Multi-page overflow will reuse the existing `messages` table by
  inserting one row per page with reduced `dwell_seconds` — no schema
  change needed, since the existing least-recently-shown tie-break
  naturally cycles pages in order.
