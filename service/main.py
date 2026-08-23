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
from .compose import BLANK_GRID, CHARSET_VERSION, text_to_grid
from .selection import Selector

WEB_DIR = Path(__file__).resolve().parent / "web"

selector = Selector()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    yield


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


def _row_to_out(row) -> MessageOut:
    return MessageOut(
        id=row["id"],
        text=row["raw_text"] or "",
        priority=row["priority"],
        dwell_seconds=row["dwell_seconds"],
        pinned=bool(row["pinned"]),
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

    return {
        "id": message_id,
        "cells": cells,
        "charset_version": CHARSET_VERSION,
        "sound_enabled": True,
        "brightness": 1.0,
    }


@app.post("/message", response_model=MessageOut)
def post_message(msg: MessageIn):
    grid = text_to_grid(msg.text)
    conn = db.get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO messages "
            "(source, raw_text, grid, priority, dwell_seconds, starts_at, expires_at, pinned) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "manual",
                msg.text,
                json.dumps(grid),
                msg.priority,
                msg.dwell_seconds,
                msg.starts_at.timestamp() if msg.starts_at else None,
                msg.expires_at.timestamp() if msg.expires_at else None,
                int(msg.pinned),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone()
    finally:
        conn.close()
    return _row_to_out(row)


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
