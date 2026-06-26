"""Geo API — places, events, and a backfill trigger (Lane B).

A self-contained ``APIRouter`` (prefix ``/api/geo``). It is **NOT registered**
here — the orchestrator adds ``app.include_router(routes_geo.router)`` to
``webui/main.py`` (see the lane report's CENTRAL WIRING).

Reads use plain ``sqlite3`` against the configured catalog path (resolved the
same way ``webui/main.py`` does), so this module adds no ORM model and stays
read-only on the listing side. The backfill endpoint dispatches to
``pipeline.geo.backfill`` and defaults to ``dry_run=True`` (writes nothing).

Tests inject a temp DB via :func:`set_database`, mirroring how the existing
endpoint tests monkeypatch ``webui.main.db``.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from pipeline.database import Database
from pipeline.geo import backfill as geo_backfill
from webui.auth_routes import require_admin

router = APIRouter(prefix="/api/geo", tags=["geo"])

_db: Database | None = None


def set_database(db: Database) -> None:
    """Inject the catalog handle (used at registration time and by tests)."""
    global _db
    _db = db


def _default_db() -> Database:
    """Resolve the catalog from the typed settings (same path as webui/main.py)."""
    from pipeline.settings import settings

    return Database(str(settings.database_path))


def get_database() -> Database:
    global _db
    if _db is None:
        _db = _default_db()
    return _db


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_database().db_path)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/places")
async def list_places() -> list[dict[str, Any]]:
    """Places with how many images resolve to each (descending by count)."""
    conn = _conn()
    try:
        rows = conn.execute(
            """
            SELECT p.id, p.name, p.admin1, p.cc, p.lat, p.lon,
                   COUNT(i.id) AS image_count
            FROM places p
            LEFT JOIN images i ON i.place_id = p.id
            GROUP BY p.id
            ORDER BY image_count DESC, p.name
            """
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.get("/events")
async def list_events() -> list[dict[str, Any]]:
    """Auto-albums (events), newest first."""
    conn = _conn()
    try:
        rows = conn.execute(
            """
            SELECT id, start_time, end_time, centroid_lat, centroid_lon,
                   member_count, label
            FROM events
            ORDER BY start_time DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.get("/events/{event_id}")
async def event_detail(event_id: int) -> dict[str, Any]:
    """One event plus its member image ids."""
    conn = _conn()
    try:
        event = conn.execute(
            "SELECT id, start_time, end_time, centroid_lat, centroid_lon, "
            "member_count, label FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if event is None:
            raise HTTPException(status_code=404, detail=f"event {event_id} not found")
        members = conn.execute(
            "SELECT owner_type, owner_id FROM event_members WHERE event_id = ? "
            "ORDER BY owner_id",
            (event_id,),
        ).fetchall()
    finally:
        conn.close()
    detail = dict(event)
    detail["members"] = [dict(m) for m in members]
    return detail


@router.post("/backfill")
async def trigger_backfill(
    payload: dict[str, Any] = Body(default={}),
    _: None = Depends(require_admin),
) -> dict[str, Any]:
    """Trigger a backfill stage (admin-only when auth is on; audit P1).

    Body: ``{"stage": "gps"|"places"|"events"|"scene_tags", "dry_run": true}``.
    ``dry_run`` defaults to ``True`` — a dry run reports counts and writes
    nothing. A real run requires an explicit ``"dry_run": false`` AND a prior DB
    backup (the operator's responsibility).
    """
    stage = payload.get("stage")
    dry_run = bool(payload.get("dry_run", True))
    if not stage:
        raise HTTPException(status_code=422, detail="missing 'stage'")
    try:
        return geo_backfill.run_stage(get_database(), stage, dry_run=dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
