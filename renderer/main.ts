import { Board, Charset } from "../engine/index.js";
import { BoardCanvas } from "./canvas.js";
import { BoardAudio } from "./audio.js";
import { enableKiosk } from "./kiosk.js";

const ROWS = 6;
const COLS = 22;
const FLAP_MS = 28;
const POLL_URL = "/current";
const POLL_INTERVAL_MS = 5000;

const charset = Charset.load();
const board = new Board(charset, { rows: ROWS, cols: COLS, flapMs: FLAP_MS, startJitterMs: 20 });

const canvasEl = document.getElementById("board") as HTMLCanvasElement;
const renderer = new BoardCanvas(canvasEl, charset, ROWS, COLS);
renderer.resize();
renderer.renderAll(board.cells);

window.addEventListener("resize", () => {
  renderer.resize();
  renderer.renderAll(board.cells);
});

const audio = new BoardAudio();
enableKiosk();
window.addEventListener("pointerdown", () => audio.resume(), { once: true });
window.addEventListener("keydown", () => audio.resume(), { once: true });

// Flap events do double duty: schedule the click, and catch the exact frame
// a cell settles (remaining hits 0 mid-tick, so it drops out of the
// "still animating" scan below on that same frame).
let settledThisFrame = new Set<number>();
board.on("flap", (e) => {
  audio.scheduleFlap(e.timestamp);
  if (e.code === board.cells[e.cellIndex].target) settledThisFrame.add(e.cellIndex);
});

let last = performance.now();
function frame(now: number): void {
  const dt = now - last;
  last = now;

  board.tick(dt);

  const dirty = settledThisFrame;
  settledThisFrame = new Set();
  for (let i = 0; i < board.cells.length; i++) {
    if (board.cells[i].remaining > 0) dirty.add(i);
  }
  if (dirty.size > 0) renderer.renderDirty(board.cells, dirty);

  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

interface CurrentPayload {
  id: number | null;
  cells: number[];
  charset_version: number;
  sound_enabled: boolean;
  brightness: number;
}

let warnedVersionMismatch = false;

async function poll(): Promise<void> {
  try {
    const res = await fetch(POLL_URL, { cache: "no-store" });
    if (!res.ok) return;
    const data = (await res.json()) as CurrentPayload;

    // Refuse a payload built against a charset we don't agree with — showing
    // wrong letters is worse than showing stale ones.
    if (data.charset_version !== charset.version) {
      if (!warnedVersionMismatch) {
        console.warn(
          `charset_version mismatch: renderer has ${charset.version}, service sent ${data.charset_version}. Ignoring payload.`
        );
        warnedVersionMismatch = true;
      }
      return;
    }
    warnedVersionMismatch = false;

    board.setTarget(data.cells);
    audio.setGain(data.sound_enabled ? 1 : 0);
  } catch {
    // LAN board, service may not be up yet — a failed fetch just means "nothing changed."
  }
}
poll();
setInterval(poll, POLL_INTERVAL_MS);
