"""Capabilities API — which gated server features are available.

Drives the frontend module registry: a module with `gate: 'faces'` is hidden
when capabilities.faces is false. Distinct from USER visibility (ui-prefs hidden);
this is the SERVER gate.

  faces   -> privacy opt-in (config/env flag; OFF by default).
  video   -> data-presence: any rows in the `videos` table. Videos can't be added
             in-app, so an empty Videos module is a dead end — hide it.
  geo     -> data-presence: any geocoded image or place. Places + Events derive
             from geo, so they stay hidden until the geo backfill has run.
  license -> always true: the license system is always available, and Free users
             must SEE Pro features to be able to buy them. No content is gated.

The data-presence helpers query raw SQL defensively and return False on any error
(missing table/column) so /api/capabilities always answers.
"""

from __future__ import annotations

from fastapi import APIRouter

from pipeline.faces.config import faces_enabled
from webui import deps

router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])


def _count_positive(db, *queries: str) -> bool:
    """True iff any of the given COUNT queries returns > 0. False on any error.

    Each query is tried independently so a missing table/column in one does not
    suppress a positive result from another.
    """
    from sqlalchemy import text

    try:
        with db.get_session() as session:
            for q in queries:
                try:
                    if int(session.execute(text(q)).scalar() or 0) > 0:
                        return True
                except Exception:
                    continue
    except Exception:
        return False
    return False


def _has_videos(db) -> bool:
    """True iff the `videos` table has any rows."""
    return _count_positive(db, "SELECT COUNT(*) FROM videos")


def _has_geo(db) -> bool:
    """True iff any place exists or any image is geocoded (gps_lat)."""
    return _count_positive(
        db,
        "SELECT COUNT(*) FROM places",
        "SELECT COUNT(*) FROM images WHERE gps_lat IS NOT NULL",
    )


@router.get("")
def capabilities() -> dict[str, bool]:
    db = deps.db
    return {
        "faces": faces_enabled(),
        "geo": _has_geo(db),
        "video": _has_videos(db),
        "license": True,
    }
