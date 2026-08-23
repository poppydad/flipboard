/**
 * Simulates the engine against a sequence of text messages and prints
 * per-transition flap stats plus the settled board as text.
 *
 * Usage: npm run sim -- "HELLO" "WORLD"
 */
import { Board, Charset } from "../engine/index.js";

const ROWS = 6;
const COLS = 22;
const FLAP_MS = 28;

function textToGrid(charset: Charset, text: string): number[] {
  const upper = text.toUpperCase().slice(0, ROWS * COLS);
  const codes: number[] = [];
  for (const ch of upper) {
    const code = charset.codeFor(ch);
    codes.push(code ?? charset.blankCode); // unknown chars drop to blank, never crash
  }
  while (codes.length < ROWS * COLS) codes.push(charset.blankCode);
  return codes;
}

function main() {
  const messages = process.argv.slice(2);
  if (messages.length === 0) {
    console.log('Usage: npm run sim -- "HELLO" "WORLD"');
    process.exit(1);
  }

  const charset = Charset.load();
  const board = new Board(charset, { rows: ROWS, cols: COLS, flapMs: FLAP_MS, startJitterMs: 20 });

  console.log(`Charset size (N): ${charset.size}`);
  console.log(`Grid: ${ROWS}x${COLS} = ${ROWS * COLS} cells`);
  console.log(`Flap rate: ${FLAP_MS}ms/flap\n`);

  for (const msg of messages) {
    const before = board.currentGrid().flat();
    const target = textToGrid(charset, msg);
    board.setTarget(target);

    let flapCount = 0;
    const listener = () => flapCount++;
    board.on("flap", listener);

    let ticks = 0;
    const dt = 16; // ~60fps
    while (!board.isSettled && ticks < 100_000) {
      board.tick(dt);
      ticks++;
    }
    board.off(listener);

    const wrapDistances = target.map((t, i) => (t - before[i] + board.n) % board.n);
    const maxWrap = Math.max(...wrapDistances);
    const totalMs = ticks * dt;

    console.log(`> "${msg}"`);
    console.log(`  flaps fired: ${flapCount}  |  slowest cell: ${maxWrap} flaps  |  settle time: ~${totalMs}ms`);
    console.log(
      board
        .toText()
        .split("\n")
        .map((line) => `  |${line}|`)
        .join("\n")
    );
    console.log();
  }
}

main();
