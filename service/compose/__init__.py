"""
The layout engine (build plan §10): text -> legal charset codes -> word
wrap -> centered placement -> one or more 6x22 grids. Pure functions, no
I/O — service/main.py owns turning `render()`'s pages into stored
messages.

This is what replaces service/compose.py's Phase 2 placeholder wholesale.
"""
from .align import align
from .charset import BLANK_CODE, BLANK_GRID, CHARSET, CHARSET_VERSION, COLS, ROWS
from .normalize import normalize
from .render import decode, render
from .smart import pick as pick_smart_template
from .templates import TEMPLATES, banner, chips, countdown, list_template, stat
from .wrap import wrap

__all__ = [
    "align",
    "decode",
    "banner",
    "BLANK_CODE",
    "BLANK_GRID",
    "CHARSET",
    "CHARSET_VERSION",
    "chips",
    "COLS",
    "countdown",
    "list_template",
    "normalize",
    "pick_smart_template",
    "render",
    "ROWS",
    "stat",
    "TEMPLATES",
    "wrap",
]
