import { Charset } from "../engine/index.js";
import type { CellState } from "../engine/index.js";

export interface TileMetrics {
  tileW: number;
  tileH: number;
  gap: number;
  originX: number;
  originY: number;
  fontSize: number;
}

const TILE_BG = "#161616";
const TILE_INSET = "#050505";
const CHAR_FG = "#e8e4d8";
const SPLIT_LINE = "rgba(0,0,0,0.85)";

export class BoardCanvas {
  private readonly ctx: CanvasRenderingContext2D;
  private readonly n: number;
  private metrics: TileMetrics;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly charset: Charset,
    private readonly rows: number,
    private readonly cols: number
  ) {
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("2D canvas context unavailable");
    this.ctx = ctx;
    this.n = charset.size;
    this.metrics = this.computeMetrics();
  }

  /** Recomputes tile size/origin from the current canvas pixel size. Call after any resize. */
  resize(): void {
    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.round(rect.width * dpr);
    this.canvas.height = Math.round(rect.height * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.metrics = this.computeMetrics();
  }

  private computeMetrics(): TileMetrics {
    const dpr = window.devicePixelRatio || 1;
    const cssW = this.canvas.width / dpr;
    const cssH = this.canvas.height / dpr;

    const gap = Math.max(2, Math.floor(cssW / this.cols) * 0.06);
    const tileW = (cssW - gap * (this.cols + 1)) / this.cols;
    const tileH = (cssH - gap * (this.rows + 1)) / this.rows;
    const fontSize = this.fitFontSize(tileW, tileH);

    return { tileW, tileH, gap, originX: gap, originY: gap, fontSize };
  }

  /**
   * A physical flap can't grow to fit a wide glyph — the module is a fixed
   * size, so the whole charset has to share one font size that the widest
   * character (M/W/% etc.) still fits inside. Sizing purely off tileH (the
   * old behavior) clips wide letters whenever a cell's aspect ratio gets
   * narrow — e.g. a tall, narrow window. Shrink until every character in
   * the charset measures within tileW.
   */
  private fitFontSize(tileW: number, tileH: number): number {
    let size = tileH * 0.62;
    this.ctx.font = `700 ${Math.floor(size)}px "Helvetica Neue", Arial, sans-serif`;
    let maxWidth = 0;
    for (const f of this.charset.flaps) {
      if (!f.char || f.char === " ") continue;
      maxWidth = Math.max(maxWidth, this.ctx.measureText(f.char).width);
    }
    const budget = tileW * 0.92;
    if (maxWidth > budget && maxWidth > 0) {
      size = size * (budget / maxWidth);
    }
    return size;
  }

  /** Full redraw of every cell — used for the initial paint and full-board changes. */
  renderAll(cells: readonly CellState[]): void {
    this.ctx.fillStyle = "#000";
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    for (let i = 0; i < cells.length; i++) {
      this.drawTile(i, cells[i]);
    }
  }

  /** Redraws only the given cell indices — the dirty-tile path used every animation frame. */
  renderDirty(cells: readonly CellState[], dirty: Iterable<number>): void {
    for (const i of dirty) {
      this.drawTile(i, cells[i]);
    }
  }

  private tileOrigin(index: number): { x: number; y: number } {
    const row = Math.floor(index / this.cols);
    const col = index % this.cols;
    const { tileW, tileH, gap, originX, originY } = this.metrics;
    return {
      x: originX + col * (tileW + gap),
      y: originY + row * (tileH + gap),
    };
  }

  private drawTile(index: number, cell: CellState): void {
    const { x, y } = this.tileOrigin(index);
    const { tileW, tileH, gap } = this.metrics;
    const midY = y + tileH / 2;

    // Recessed well behind the tile — the gap itself does most of the "texture" work.
    this.ctx.fillStyle = TILE_INSET;
    this.ctx.fillRect(x - gap * 0.4, y - gap * 0.4, tileW + gap * 0.8, tileH + gap * 0.8);

    this.ctx.fillStyle = TILE_BG;
    this.ctx.fillRect(x, y, tileW, tileH);

    const animating = cell.remaining > 0;
    const outgoing = cell.current;
    const incoming = animating ? (cell.current + 1) % this.n : cell.current;
    const theta = animating ? cell.phase * Math.PI : 0;

    // Static halves behind the leaf: top already shows what's coming in, bottom
    // still shows what's on its way out — the leaf is what covers the seam.
    this.drawHalf(incoming, x, y, tileW, tileH, { x, y, w: tileW, h: tileH / 2 });
    this.drawHalf(outgoing, x, y, tileW, tileH, { x, y: midY, w: tileW, h: tileH - tileH / 2 });

    if (animating) {
      const scaleY = Math.abs(Math.cos(theta));
      const edgeOnness = Math.sin(theta); // 0 flat, 1 at the 90° edge-on point
      const cx = x + tileW / 2;

      // Cast shadow: the rotating leaf darkens the seam of the half it's swinging
      // over, peaking as it goes edge-on directly above/below the midline.
      if (edgeOnness > 0.02) {
        const castH = (tileH / 2) * 0.4;
        this.ctx.save();
        if (theta <= Math.PI / 2) {
          const grad = this.ctx.createLinearGradient(0, midY, 0, midY + castH);
          grad.addColorStop(0, `rgba(0,0,0,${0.55 * edgeOnness})`);
          grad.addColorStop(1, "rgba(0,0,0,0)");
          this.ctx.fillStyle = grad;
          this.ctx.fillRect(x, midY, tileW, castH);
        } else {
          const grad = this.ctx.createLinearGradient(0, midY, 0, midY - castH);
          grad.addColorStop(0, `rgba(0,0,0,${0.55 * edgeOnness})`);
          grad.addColorStop(1, "rgba(0,0,0,0)");
          this.ctx.fillStyle = grad;
          this.ctx.fillRect(x, midY - castH, tileW, castH);
        }
        this.ctx.restore();
      }

      this.ctx.save();
      if (theta <= Math.PI / 2) {
        // First half of the fold: the outgoing top swings down toward edge-on.
        this.ctx.beginPath();
        this.ctx.rect(x, y, tileW, tileH / 2);
        this.ctx.clip();
        this.ctx.translate(cx, midY);
        this.ctx.scale(1, scaleY);
        this.ctx.translate(-cx, -midY);
        this.paintGlyph(outgoing, x, y, tileW, tileH);
        this.paintFoldShade(x, y, tileW, midY, edgeOnness, /* hingeAtBottom */ true);
      } else {
        // Second half: the incoming bottom continues the rotation down to flush.
        this.ctx.beginPath();
        this.ctx.rect(x, midY, tileW, tileH - tileH / 2);
        this.ctx.clip();
        this.ctx.translate(cx, midY);
        this.ctx.scale(1, scaleY);
        this.ctx.translate(-cx, -midY);
        this.paintGlyph(incoming, x, y, tileW, tileH);
        this.paintFoldShade(x, midY, tileW, y + tileH, edgeOnness, /* hingeAtBottom */ false);
      }
      this.ctx.restore();
    }

    // Split line — the seam between the fixed upper and lower panels. Always
    // visible, even settled; without it the board reads as a font, not a mechanism.
    this.ctx.fillStyle = SPLIT_LINE;
    this.ctx.fillRect(x, midY - Math.max(1, tileH * 0.008), tileW, Math.max(2, tileH * 0.016));
  }

  /**
   * Darkens the leaf face itself: a crease gradient (darkest at the hinge,
   * lightest at the free edge) plus a uniform wash that peaks as the leaf
   * turns edge-on — the combination is most of what reads as "3D" here.
   */
  private paintFoldShade(
    x: number,
    edgeY: number,
    tileW: number,
    hingeY: number,
    edgeOnness: number,
    hingeAtBottom: boolean
  ): void {
    const grad = hingeAtBottom
      ? this.ctx.createLinearGradient(0, edgeY, 0, hingeY)
      : this.ctx.createLinearGradient(0, hingeY, 0, edgeY);
    const creaseAlpha = 0.5;
    grad.addColorStop(0, `rgba(0,0,0,${0.08 + 0.1 * edgeOnness})`);
    grad.addColorStop(1, `rgba(0,0,0,${creaseAlpha + 0.3 * edgeOnness})`);
    this.ctx.fillStyle = grad;
    this.ctx.fillRect(x, Math.min(edgeY, hingeY), tileW, Math.abs(hingeY - edgeY));
  }

  private drawHalf(
    code: number,
    tileX: number,
    tileY: number,
    tileW: number,
    tileH: number,
    clip: { x: number; y: number; w: number; h: number }
  ): void {
    this.ctx.save();
    this.ctx.beginPath();
    this.ctx.rect(clip.x, clip.y, clip.w, clip.h);
    this.ctx.clip();
    this.paintGlyph(code, tileX, tileY, tileW, tileH);
    this.ctx.restore();
  }

  private paintGlyph(code: number, x: number, y: number, tileW: number, tileH: number): void {
    const def = this.charset.defFor(code);
    if (def.type === "chip") {
      this.ctx.fillStyle = def.color ?? "#888";
      this.ctx.fillRect(x, y, tileW, tileH);
      return;
    }
    if (!def.char) return;
    this.ctx.fillStyle = CHAR_FG;
    this.ctx.font = `700 ${Math.floor(this.metrics.fontSize)}px "Helvetica Neue", Arial, sans-serif`;
    this.ctx.textAlign = "center";
    this.ctx.textBaseline = "middle";
    this.ctx.fillText(def.char, x + tileW / 2, y + tileH / 2 + tileH * 0.03);
  }
}
