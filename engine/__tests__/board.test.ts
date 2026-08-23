import { describe, expect, it } from "vitest";
import { Charset } from "../charset.js";
import { Board } from "../board.js";

function makeBoard(rows = 1, cols = 1, flapMs = 10, startJitterMs = 0) {
  const charset = Charset.load();
  const board = new Board(charset, { rows, cols, flapMs, startJitterMs });
  return { charset, board };
}

function runToSettled(board: Board, dt = 5, maxTicks = 200_000): number {
  let ticks = 0;
  while (!board.isSettled && ticks < maxTicks) {
    board.tick(dt);
    ticks++;
  }
  if (ticks >= maxTicks) throw new Error("Board did not settle within maxTicks — possible infinite loop");
  return ticks;
}

describe("Charset", () => {
  it("loads the spec with the expected size and no gaps", () => {
    const charset = Charset.load();
    expect(charset.size).toBe(63);
    expect(charset.flaps[0].type).toBe("blank");
  });

  it("resolves letters, digits, and punctuation to codes and back", () => {
    const charset = Charset.load();
    expect(charset.codeFor("A")).toBe(1);
    expect(charset.codeFor("Z")).toBe(26);
    expect(charset.charFor(charset.codeFor("5")!)).toBe("5");
  });

  it("applies transliteration for accented characters", () => {
    const charset = Charset.load();
    expect(charset.codeFor("É")).toBe(charset.codeFor("E"));
  });

  it("has no character-bearing code shared between two characters", () => {
    const charset = Charset.load();
    const seen = new Map<string, number>();
    for (const f of charset.flaps) {
      if (f.char == null) continue;
      expect(seen.has(f.char)).toBe(false);
      seen.set(f.char, f.code);
    }
  });
});

describe("Board flap physics", () => {
  it("A -> C takes exactly 2 flaps", () => {
    const { charset, board } = makeBoard();
    board.setTarget([charset.codeFor("A")!]);
    runToSettled(board);

    let flapCount = 0;
    board.on("flap", () => flapCount++);
    board.setTarget([charset.codeFor("C")!]);
    runToSettled(board);

    expect(flapCount).toBe(2);
    expect(board.cells[0].current).toBe(charset.codeFor("C"));
  });

  it("a cell already at its target produces zero flap events", () => {
    const { charset, board } = makeBoard();
    board.setTarget([charset.codeFor("Q")!]);
    runToSettled(board);

    let flapCount = 0;
    board.on("flap", () => flapCount++);
    board.setTarget([charset.codeFor("Q")!]); // same target again
    board.tick(1000);

    expect(flapCount).toBe(0);
    expect(board.isSettled).toBe(true);
  });

  it("wrap distance is forward-only: Z -> B takes the long way around, matching the formula", () => {
    const { charset, board } = makeBoard();
    const z = charset.codeFor("Z")!;
    const b = charset.codeFor("B")!;
    board.setTarget([z]);
    runToSettled(board);

    let flapCount = 0;
    board.on("flap", () => flapCount++);
    board.setTarget([b]);
    const expectedSteps = (b - z + board.n) % board.n;
    runToSettled(board);

    expect(flapCount).toBe(expectedSteps);
    expect(board.cells[0].current).toBe(b);
  });

  it("settle order across a full-board change is monotonic in wrap distance", () => {
    // Three cells with deliberately different wrap distances from blank.
    // The one with the fewest flaps must settle first (fewest ticks to zero remaining).
    const { charset, board } = makeBoard(1, 3, 10, 0);
    const targets = [charset.codeFor("B")!, charset.codeFor("M")!, charset.codeFor("Y")!]; // 2, 13, 25 flaps from blank
    board.setTarget(targets);

    const settledAtTick: (number | null)[] = [null, null, null];
    let tick = 0;
    while (!board.isSettled && tick < 10_000) {
      board.tick(1);
      tick++;
      board.cells.forEach((c, i) => {
        if (c.remaining === 0 && settledAtTick[i] === null) settledAtTick[i] = tick;
      });
    }

    expect(settledAtTick[0]).toBeLessThan(settledAtTick[1]!);
    expect(settledAtTick[1]).toBeLessThan(settledAtTick[2]!);
  });

  it("retargeting mid-animation redirects from the live position, not the original grid", () => {
    const { charset, board } = makeBoard(1, 1, 10, 0);
    board.setTarget([charset.codeFor("A")!]);
    runToSettled(board); // settle at A first, so the next trip has a known, non-zero start

    const startCode = board.cells[0].current; // A
    board.setTarget([charset.blankCode]); // long forward trip: A -> ... -> blank (62 flaps)
    board.tick(10 * 5); // advance partway — 5 flaps in
    const midCode = board.cells[0].current;
    expect(midCode).not.toBe(startCode);

    // Retarget somewhere new before the first trip finishes.
    board.setTarget([charset.codeFor("K")!]);
    const expectedFromMid = (charset.codeFor("K")! - midCode + board.n) % board.n;
    expect(board.cells[0].remaining).toBe(expectedFromMid);

    // The bug this test guards against: computing remaining from `startCode`
    // (the pre-retarget origin) instead of `midCode` (the live position).
    const wrongIfComputedFromOldOrigin = (charset.codeFor("K")! - startCode + board.n) % board.n;
    expect(board.cells[0].remaining).not.toBe(wrongIfComputedFromOldOrigin);

    runToSettled(board);
    expect(board.cells[0].current).toBe(charset.codeFor("K"));
  });

  it("rejects a grid of the wrong size", () => {
    const { board } = makeBoard(6, 22);
    expect(() => board.setTarget(new Array(10).fill(0))).toThrow(/size mismatch/i);
  });

  it("rejects an illegal code", () => {
    const { board } = makeBoard(1, 1);
    expect(() => board.setTarget([9999])).toThrow(/illegal code/i);
  });

  it("accepts nested row-major grids the same as flat arrays", () => {
    const { charset, board } = makeBoard(2, 2);
    const code = charset.codeFor("Q")!;
    board.setTarget([
      [code, code],
      [code, code],
    ]);
    runToSettled(board);
    expect(board.currentGrid()).toEqual([
      [code, code],
      [code, code],
    ]);
  });

  it("a full 6x22 board settles within the expected max tick budget", () => {
    const { charset, board } = makeBoard(6, 22, 28, 0);
    const grid = Array.from({ length: 6 }, () =>
      Array.from({ length: 22 }, () => Math.floor(Math.random() * board.n))
    );
    board.setTarget(grid);

    const maxSteps = board.n - 1;
    const maxMs = maxSteps * board.flapMs;
    const dt = 16; // ~60fps
    const maxTicks = Math.ceil(maxMs / dt) + 2;

    const actualTicks = runToSettled(board, dt, maxTicks + 10);
    expect(actualTicks).toBeLessThanOrEqual(maxTicks);
    expect(board.currentGrid()).toEqual(grid);
    expect(board.isSettled).toBe(true);
  });

  it("total flap events emitted equals the sum of per-cell wrap distances", () => {
    const { charset, board } = makeBoard(1, 4, 10, 0);
    const targets = [charset.codeFor("B")!, charset.codeFor("Z")!, charset.blankCode, charset.codeFor("5")!];
    const expectedTotal = targets.reduce((sum, t) => sum + t, 0); // all starting from blank (code 0)

    let flapCount = 0;
    board.on("flap", () => flapCount++);
    board.setTarget(targets);
    runToSettled(board);

    expect(flapCount).toBe(expectedTotal);
  });

  it("flap events carry monotonically increasing flapIndex per cell within one transition", () => {
    const { charset, board } = makeBoard(1, 1, 10, 0);
    board.setTarget([charset.codeFor("M")!]);

    const seenIndices: number[] = [];
    board.on("flap", (e) => seenIndices.push(e.flapIndex));
    runToSettled(board);

    expect(seenIndices).toEqual([...Array(seenIndices.length)].map((_, i) => i + 1));
  });

  it("start jitter delays animation start but does not change total flap count", () => {
    const { charset, board } = makeBoard(1, 1, 10, 500);
    let flapCount = 0;
    board.on("flap", () => flapCount++);
    board.setTarget([charset.codeFor("F")!]);
    runToSettled(board, 5);
    expect(flapCount).toBe(charset.codeFor("F"));
  });
});
