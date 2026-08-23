import { describe, expect, it } from "vitest";
import { createCell, setCellTarget, tickCell } from "../cell.js";

const N = 63; // matches spec/charset.json size, kept local so this file doesn't depend on it

function runToSettled(cell: ReturnType<typeof createCell>, dt: number, n: number, flapMs: number, onFlap?: () => void) {
  let ticks = 0;
  while ((cell.remaining > 0 || cell.startDelay > 0) && ticks < 1_000_000) {
    tickCell(cell, dt, n, flapMs, onFlap);
    ticks++;
  }
  return ticks;
}

describe("cell state machine", () => {
  it("starts settled at its initial value", () => {
    const cell = createCell(5);
    expect(cell.current).toBe(5);
    expect(cell.target).toBe(5);
    expect(cell.remaining).toBe(0);
  });

  it("setting the same target as current produces zero remaining flaps", () => {
    const cell = createCell(10);
    setCellTarget(cell, 10, N);
    expect(cell.remaining).toBe(0);
    let flapped = false;
    tickCell(cell, 1000, N, 28, () => (flapped = true));
    expect(flapped).toBe(false);
  });

  it("computes forward wrap distance, never backward", () => {
    const cell = createCell(1); // A
    setCellTarget(cell, 3, N); // -> C
    expect(cell.remaining).toBe(2);
  });

  it("wraps forward across the top of the charset (Z -> B goes forward, not back to B directly)", () => {
    const Z = 26;
    const B = 2;
    const cell = createCell(Z);
    setCellTarget(cell, B, N);
    const expectedSteps = (B - Z + N) % N;
    expect(cell.remaining).toBe(expectedSteps);
    expect(expectedSteps).toBeGreaterThan(N / 2); // confirms it's genuinely the "long way around" case
  });

  it("fires exactly one flap event per flapMs of elapsed time", () => {
    const cell = createCell(0);
    setCellTarget(cell, 5, N);
    let count = 0;
    tickCell(cell, 28 * 3.5, N, 28, () => count++); // 3.5 flap-durations worth of time
    expect(count).toBe(3);
    expect(cell.remaining).toBe(2);
  });

  it("a single large dt can cross multiple flaps in one call", () => {
    const cell = createCell(0);
    setCellTarget(cell, 10, N);
    let count = 0;
    tickCell(cell, 28 * 100, N, 28, () => count++); // way more time than needed
    expect(count).toBe(10);
    expect(cell.current).toBe(10);
    expect(cell.remaining).toBe(0);
  });

  it("settles exactly on target with correct total flap count", () => {
    const cell = createCell(40);
    setCellTarget(cell, 12, N);
    const expectedSteps = (12 - 40 + N) % N;
    let count = 0;
    runToSettled(cell, 5, N, 28, () => count++);
    expect(cell.current).toBe(12);
    expect(count).toBe(expectedSteps);
  });

  it("respects startDelay before consuming any flap time", () => {
    const cell = createCell(0);
    setCellTarget(cell, 1, N, 1000); // force a jittered delay up to 1000ms
    cell.startDelay = 500; // pin it deterministically for the test
    let flapped = false;
    tickCell(cell, 100, N, 28, () => (flapped = true));
    expect(flapped).toBe(false);
    expect(cell.startDelay).toBe(400);
  });

  it("retargeting mid-flight redirects from the CURRENT position, not the original start", () => {
    // This is the regression the split-engine design exists to catch:
    // a naive implementation might compute remaining from the cell's
    // original target rather than its live position.
    const cell = createCell(0);
    setCellTarget(cell, 20, N); // long trip: 20 flaps
    let count = 0;
    tickCell(cell, 28 * 5, N, 28, () => count++); // advance 5 flaps -> current = 5
    expect(cell.current).toBe(5);
    expect(count).toBe(5);

    // Retarget now, mid-flight, to somewhere else entirely.
    setCellTarget(cell, 8, N);
    const expectedFromHere = (8 - 5 + N) % N;
    expect(cell.remaining).toBe(expectedFromHere);
    expect(cell.remaining).not.toBe((8 - 0 + N) % N); // sanity: not computed from the old origin

    let secondCount = 0;
    runToSettled(cell, 5, N, 28, () => secondCount++);
    expect(cell.current).toBe(8);
    expect(secondCount).toBe(expectedFromHere);
  });
});
