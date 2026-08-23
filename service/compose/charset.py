"""
Loads spec/charset.json for the layout engine. Reuses the one shared
Python loader (python/charset.py) rather than duplicating it — see
CLAUDE.md: "Charset is one JSON file, two loaders," and the two loaders
are engine/charset.ts and python/charset.py. This is not a third one.
"""
from charset import Charset  # service/__init__.py puts python/ on sys.path

ROWS = 6
COLS = 22

CHARSET = Charset.load()
CHARSET_VERSION = CHARSET.version
BLANK_CODE = CHARSET.blank_code
BLANK_GRID = [BLANK_CODE] * (ROWS * COLS)
