/**
 * One cell's flap state.
 *
 * A cell doesn't know duration — it knows a target and a rate. Duration
 * falls out of wrap distance: (target - current) mod N flaps, each taking
 * a fixed flapMs. This is the whole trick that makes the settle cascade
 * look real instead of staggered-by-hand.
 */
export interface CellState {
  /** Flap index currently showing. */
  current: number;
  /** Flap index this cell is animating toward. */
  target: number;
  /** Flaps remaining before `current === target`. */
  remaining: number;
  /** Ms accumulated toward the next flap. */
  elapsed: number;
  /** 0..1 progress through the current flap — for the renderer's fold angle. */
  phase: number;
  /** Ms of jittered delay remaining before this cell starts animating. */
  startDelay: number;
}

export function createCell(initial: number): CellState {
  return { current: initial, target: initial, remaining: 0, elapsed: 0, phase: 0, startDelay: 0 };
}

/**
 * Points a cell at a new target. Retargets from wherever the cell currently
 * is — including mid-flap — never from its original starting position.
 * (This is the behavior that's invisible without a test: see
 * "retargeting mid-animation" in board.test.ts.)
 */
export function setCellTarget(cell: CellState, target: number, n: number, jitterMs = 0): void {
  const t = ((target % n) + n) % n;
  cell.target = t;
  cell.remaining = (t - cell.current + n) % n;
  cell.elapsed = 0;
  cell.phase = 0;
  cell.startDelay = cell.remaining > 0 && jitterMs > 0 ? Math.random() * jitterMs : 0;
}

/**
 * Advances a cell by dt milliseconds. Fires onFlap once per physical flap
 * crossed — a large dt can cross several flaps in one call, which matters
 * for low frame rates or fast-forwarding in tests.
 */
export function tickCell(cell: CellState, dt: number, n: number, flapMs: number, onFlap?: () => void): void {
  if (cell.remaining === 0) {
    cell.phase = 0;
    return;
  }

  if (cell.startDelay > 0) {
    cell.startDelay -= dt;
    return;
  }

  cell.elapsed += dt;
  while (cell.elapsed >= flapMs && cell.remaining > 0) {
    cell.elapsed -= flapMs;
    cell.current = (cell.current + 1) % n;
    cell.remaining -= 1;
    onFlap?.();
  }

  cell.phase = cell.remaining > 0 ? Math.min(cell.elapsed / flapMs, 1) : 0;
}
