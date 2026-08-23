"""
Loads spec/charset.json — mirrors engine/charset.ts.

The array index of each entry IS the physical flap position. This file and
its TypeScript counterpart must never disagree about that order; see
verify_parity.py, which is the thing that actually enforces it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SPEC_PATH = Path(__file__).resolve().parent.parent / "spec" / "charset.json"


@dataclass(frozen=True)
class FlapDef:
    code: int
    char: str | None
    type: str
    color: str | None = None


class Charset:
    def __init__(self, spec: dict):
        self.version: int = spec["version"]
        self.flaps: list[FlapDef] = []
        self._char_to_code: dict[str, int] = {}
        self._transliterations: dict[str, str] = spec.get("transliterations", {})

        for i, entry in enumerate(spec["flaps"]):
            if entry["code"] != i:
                raise ValueError(
                    f"Charset spec is not contiguous: entry {i} has code {entry['code']}. "
                    "Flap order must equal array order — it IS the physical position."
                )
            flap = FlapDef(
                code=entry["code"],
                char=entry.get("char"),
                type=entry["type"],
                color=entry.get("color"),
            )
            self.flaps.append(flap)
            if flap.char is not None:
                if flap.char in self._char_to_code:
                    raise ValueError(f"Duplicate character in charset: {flap.char!r}")
                self._char_to_code[flap.char] = flap.code

        self.size = len(self.flaps)

    @classmethod
    def load(cls, path: Path = SPEC_PATH) -> "Charset":
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f))

    def code_for(self, char: str) -> int | None:
        normalized = self._transliterations.get(char, char)
        return self._char_to_code.get(normalized)

    def char_for(self, code: int) -> str | None:
        if not 0 <= code < self.size:
            raise IndexError(f"Code {code} out of range for charset of size {self.size}")
        return self.flaps[code].char

    @property
    def blank_code(self) -> int:
        for f in self.flaps:
            if f.type == "blank":
                return f.code
        raise ValueError("Charset has no blank entry")

    def to_canonical_map(self) -> dict:
        """A deterministic, JSON-serializable view used for cross-language parity checks."""
        return {
            "version": self.version,
            "size": self.size,
            "codes": [
                {"code": f.code, "char": f.char, "type": f.type, "color": f.color}
                for f in self.flaps
            ],
        }


if __name__ == "__main__":
    cs = Charset.load()
    print(f"Charset size (N): {cs.size}")
    print(f"Blank code: {cs.blank_code}")
    print(f"'A' -> {cs.code_for('A')}, 'É' -> {cs.code_for('É')} (should match 'E' = {cs.code_for('E')})")
