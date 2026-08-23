import { Charset } from "./charset.js";
import { CellState, createCell, setCellTarget, tickCell } from "./cell.js";

export interface FlapEvent {
  cellIndex: number;
  row: number;
  col: number;
  /** 1-based flap number within this cell's current transition. */
  flapIndex: number;
  /** The code now showing after this flap. */
  code: number;
  /** Engine clock time (ms) this flap landed at. */
  timestamp: number;
}

export interface BoardOptions {
  rows: number;
  cols: number;
  /** Ms per flap. Real hardware sits around 25-35ms. */
  flapMs?: number;
  /** Max random start delay (ms) before a cell begins animating. 0 = perfect unison. */
  startJitterMs?: number;
}

type FlapListener = (e: FlapEvent) => void;

export class Board {
  readonly rows: number;
  readonly cols: number;
  readonly flapMs: number;
  readonly startJitterMs: number;
  readonly n: number;
  readonly cells: CellState[];

  private readonly charset: Charset;
  private readonly listeners: FlapListener[] = [];
  private readonly flapCounters: number[];
  private clock = 0;

  constructor(charset: Charset, options: BoardOptions) {
    this.charset = charset;
    this.rows = options.rows;
    this.cols = options.cols;
    this.flapMs = options.flapMs ?? 28;
    this.startJitterMs = options.startJitterMs ?? 0;
    this.n = charset.size;

    const size = this.rows * this.cols;
    const blank = charset.blankCode;
    this.cells = Array.from({ length: size }, () => createCell(blank));
    this.flapCounters = new Array(size).fill(0);
  }

  get size(): number {
    return this.rows * this.cols;
  }

  /** Points every cell at a new target grid. Accepts flat or row-major nested arrays. */
  setTarget(grid: number[][] | number[]): void {
    const flat = Array.isArray(grid[0]) ? (grid as number[][]).flat() : (grid as number[]);
    if (flat.length !== this.size) {
      throw new Error(`Grid size mismatch: expected ${this.size} cells, got ${flat.length}`);
    }
    flat.forEach((code, i) => {
      if (!Number.isInteger(code) || code < 0 || code >= this.n) {
        throw new Error(`Illegal code ${code} at cell ${i} (charset size is ${this.n})`);
      }
      this.flapCounters[i] = 0;
      setCellTarget(this.cells[i], code, this.n, this.startJitterMs);
    });
  }

  /** Advances the whole board by dt milliseconds. */
  tick(dt: number): void {
    this.clock += dt;
    for (let i = 0; i < this.cells.length; i++) {
      const cell = this.cells[i];
      tickCell(cell, dt, this.n, this.flapMs, () => {
        this.flapCounters[i] += 1;
        this.emit({
          cellIndex: i,
          row: Math.floor(i / this.cols),
          col: i % this.cols,
          flapIndex: this.flapCounters[i],
          code: cell.current,
          timestamp: this.clock,
        });
      });
    }
  }

  get isSettled(): boolean {
    return this.cells.every((c) => c.remaining === 0 && c.startDelay <= 0);
  }

  /** Total flaps remaining across the whole board — useful for estimating settle time. */
  get totalRemainingFlaps(): number {
    return this.cells.reduce((sum, c) => sum + c.remaining, 0);
  }

  on(_event: "flap", listener: FlapListener): void {
    this.listeners.push(listener);
  }

  off(listener: FlapListener): void {
    const i = this.listeners.indexOf(listener);
    if (i >= 0) this.listeners.splice(i, 1);
  }

  private emit(e: FlapEvent): void {
    for (const l of this.listeners) l(e);
  }

  /** Current state as a row-major 6x22-style nested array of codes. */
  currentGrid(): number[][] {
    const grid: number[][] = [];
    for (let r = 0; r < this.rows; r++) {
      grid.push(this.cells.slice(r * this.cols, (r + 1) * this.cols).map((c) => c.current));
    }
    return grid;
  }

  /** Renders the current grid as text, for CLI debugging. Chips render as '#'. */
  toText(): string {
    return this.currentGrid()
      .map((row) => row.map((code) => this.charset.charFor(code) ?? "#").join(""))
      .join("\n");
  }
}
