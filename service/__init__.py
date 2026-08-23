"""
Puts the shared `python/charset.py` loader on sys.path once, so every
module under `service/` can just do `from charset import Charset`
without repeating the path hack.
"""
import sys
from pathlib import Path

_PYTHON_DIR = Path(__file__).resolve().parent.parent / "python"
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))
