"""
Phase 0 probe: proves the TS engine and the Python composer agree on the
charset. Runs the TS dump script, runs the Python loader, diffs the two
canonical views. Exit code 0 means parity; anything else means the spec
drifted between the two loaders (or one of them has a bug).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def get_ts_canonical() -> dict:
    result = subprocess.run(
        ["npx", "tsx", "cli/dump_charset.ts"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def get_py_canonical() -> dict:
    sys.path.insert(0, str(ROOT / "python"))
    from charset import Charset  # noqa: E402

    return Charset.load().to_canonical_map()


def main() -> int:
    ts = get_ts_canonical()
    py = get_py_canonical()

    if ts == py:
        print(f"PARITY OK — {ts['size']} flap positions, version {ts['version']}, TS and Python agree exactly.")
        return 0

    print("PARITY MISMATCH between TS and Python charset loaders:")
    if ts["version"] != py["version"]:
        print(f"  version: ts={ts['version']} py={py['version']}")
    if ts["size"] != py["size"]:
        print(f"  size: ts={ts['size']} py={py['size']}")

    ts_codes = {c["code"]: c for c in ts["codes"]}
    py_codes = {c["code"]: c for c in py["codes"]}
    for code in sorted(set(ts_codes) | set(py_codes)):
        if ts_codes.get(code) != py_codes.get(code):
            print(f"  code {code}: ts={ts_codes.get(code)} py={py_codes.get(code)}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
