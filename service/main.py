"""
FastAPI service — build plan §9. LAN only, no auth: it's a hallway board,
not a product. Run with:

    .venv/bin/uvicorn service.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import db
from .channels.scheduler import start_scheduler, stop_scheduler
from .compose import BLANK_GRID, CHARSET_VERSION, pick_smart_template
from .config import BRIGHTNESS_NORMAL, BRIGHTNESS_QUIET_FLOOR, is_quiet_hours
from .messages import create_message
from .selection import Selector

WEB_DIR = Path(__file__).resolve().parent / "web"

selector = Selector()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="flipboard", lifespan=lifespan)


class MessageIn(BaseModel):
    text: str
    priority: int = Field(default=50, ge=0)
    dwell_seconds: int = Field(default=300, gt=0)
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    pinned: bool = False


class MessageOut(BaseModel):
    id: int
    text: str
    priority: int
    dwell_seconds: int
    pinned: bool
    pages: int = 1


def _row_to_out(row, pages: int = 1) -> MessageOut:
    return MessageOut(
        id=row["id"],
        text=row["raw_text"] or "",
        priority=row["priority"],
        dwell_seconds=row["dwell_seconds"],
        pinned=bool(row["pinned"]),
        pages=pages,
    )


@app.get("/current")
def get_current():
    conn = db.get_connection()
    try:
        row = selector.current(conn)
    finally:
        conn.close()

    if row is None:
        cells = BLANK_GRID
        message_id = None
    else:
        cells = json.loads(row["grid"])
        message_id = row["id"]

    quiet = is_quiet_hours()
    return {
        "id": message_id,
        "cells": cells,
        "charset_version": CHARSET_VERSION,
        "sound_enabled": not quiet,
        "brightness": BRIGHTNESS_QUIET_FLOOR if quiet else BRIGHTNESS_NORMAL,
    }


@app.post("/message", response_model=MessageOut)
def post_message(msg: MessageIn):
    conn = db.get_connection()
    try:
        ids = create_message(
            conn,
            source="manual",
            text=msg.text,
            priority=msg.priority,
            dwell_seconds=msg.dwell_seconds,
            starts_at=msg.starts_at.timestamp() if msg.starts_at else None,
            expires_at=msg.expires_at.timestamp() if msg.expires_at else None,
            pinned=msg.pinned,
        )
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (ids[0],)).fetchone()
    finally:
        conn.close()
    return _row_to_out(row, pages=len(ids))


@app.post("/compose/smart", response_model=MessageOut)
def post_compose_smart(msg: MessageIn):
    """Same as POST /message, but tries the free heuristic template
    picker (service/compose/smart.py) first — countdown/stat/list shapes
    get a structured template grid instead of a plain wrapped banner.
    Text that matches nothing falls straight through to the normal
    render() path, so this is never worse than POST /message."""
    grid = pick_smart_template(msg.text)
    conn = db.get_connection()
    try:
        ids = create_message(
            conn,
            source="manual",
            grid=grid,
            text=None if grid is not None else msg.text,
            priority=msg.priority,
            dwell_seconds=msg.dwell_seconds,
            starts_at=msg.starts_at.timestamp() if msg.starts_at else None,
            expires_at=msg.expires_at.timestamp() if msg.expires_at else None,
            pinned=msg.pinned,
        )
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (ids[0],)).fetchone()
    finally:
        conn.close()
    return _row_to_out(row, pages=len(ids))


@app.get("/queue", response_model=list[MessageOut])
def get_queue():
    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT * FROM messages").fetchall()
    finally:
        conn.close()

    now = datetime.now().timestamp()
    eligible = [r for r in rows if r["expires_at"] is None or r["expires_at"] > now]
    eligible.sort(key=lambda r: (0 if r["pinned"] else 1, r["priority"]))
    return [_row_to_out(r) for r in eligible]


@app.delete("/queue/{message_id}")
def delete_queue_item(message_id: int):
    conn = db.get_connection()
    try:
        cur = conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="message not found")
    return {"deleted": message_id}


@app.post("/next")
def force_next():
    conn = db.get_connection()
    try:
        row = selector.current(conn, force=True)
    finally:
        conn.close()
    return {"id": row["id"] if row else None}


@app.get("/compose")
def compose_form():
    return FileResponse(WEB_DIR / "compose.html")
