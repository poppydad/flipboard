/**
 * Loads spec/charset.json — the single source of truth for flap order.
 *
 * The array index of each entry IS the physical flap position. This file
 * and its Python counterpart (python/charset.py) must never disagree about
 * that order. See python/verify_parity.py.
 */
import charsetData from "../spec/charset.json" with { type: "json" };

export type FlapType = "blank" | "letter" | "digit" | "punct" | "chip";

export interface FlapDef {
  code: number;
  char: string | null;
  type: FlapType;
  color?: string;
}

export interface CharsetSpec {
  version: number;
  flaps: FlapDef[];
  transliterations: Record<string, string>;
}

export class Charset {
  readonly version: number;
  readonly flaps: readonly FlapDef[];
  /** N — total number of flap positions. Wrap arithmetic is mod this value. */
  readonly size: number;

  private readonly charToCode = new Map<string, number>();

  constructor(spec: CharsetSpec) {
    this.version = spec.version;
    this.flaps = spec.flaps;
    this.size = spec.flaps.length;
    this.transliterations = spec.transliterations ?? {};

    spec.flaps.forEach((f, i) => {
      if (f.code !== i) {
        throw new Error(
          `Charset spec is not contiguous: entry ${i} has code ${f.code}. ` +
            `Flap order must equal array order — it IS the physical position.`
        );
      }
      if (f.char != null) {
        if (this.charToCode.has(f.char)) {
          throw new Error(`Duplicate character in charset: ${JSON.stringify(f.char)}`);
        }
        this.charToCode.set(f.char, f.code);
      }
    });
  }

  private readonly transliterations: Record<string, string>;

  /** Loads the canonical spec bundled at build time. */
  static load(spec?: CharsetSpec): Charset {
    return new Charset(spec ?? (charsetData as CharsetSpec));
  }

  /** Resolves a single character to its flap code, applying transliteration first. */
  codeFor(char: string): number | undefined {
    const normalized = this.transliterations[char] ?? char;
    return this.charToCode.get(normalized);
  }

  /** Resolves a flap code back to its display character (null for blank/chip). */
  charFor(code: number): string | null {
    const def = this.flaps[code];
    if (!def) throw new RangeError(`Code ${code} out of range for charset of size ${this.size}`);
    return def.char;
  }

  defFor(code: number): FlapDef {
    const def = this.flaps[code];
    if (!def) throw new RangeError(`Code ${code} out of range for charset of size ${this.size}`);
    return def;
  }

  get blankCode(): number {
    const blank = this.flaps.find((f) => f.type === "blank");
    if (!blank) throw new Error("Charset has no blank entry");
    return blank.code;
  }
}
