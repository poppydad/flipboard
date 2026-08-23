/** Dumps the TS charset as canonical JSON to stdout, for cross-language parity checks. */
import { Charset } from "../engine/index.js";

const cs = Charset.load();
const canonical = {
  version: cs.version,
  size: cs.size,
  codes: cs.flaps.map((f) => ({ code: f.code, char: f.char, type: f.type, color: f.color ?? null })),
};
process.stdout.write(JSON.stringify(canonical, null, 2));
