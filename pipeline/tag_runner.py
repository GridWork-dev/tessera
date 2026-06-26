"""
Fast-tier (Tier-0 / Tier-3) runner helpers — idempotent + restart-safe.

`images.processed` is the resume key for the fast-tier pass: an image is selected
while processed=0, and the runner sets processed=1 (plus a derived rating) only
after the requested fast tiers have written for that image. A crash leaves
unprocessed images at 0, so a re-run continues from where it stopped, in
deterministic id order (NOT ORDER BY RANDOM()).

Re-tagging (the 0.45-threshold + tag_source-schema refresh) clears an image's
existing model rows first, so stale sub-threshold tags never linger.
"""

from __future__ import annotations

import sqlite3

from sqlalchemy.orm import Session

from pipeline.database import Image, Tag

# Tag sources written by Tier-0 (cleared + rewritten on a re-tag).
TIER0_SOURCES = ("wd_eva02", "joytag")

# D2 map: WD-EVA02 rating head -> schema rating (conservative; errs toward
# flagging — questionable is treated as suggestive, explicit as nsfw).
WD_RATING_TO_SCHEMA = {
    "general": "sfw",
    "sensitive": "suggestive",
    "questionable": "suggestive",
    "explicit": "nsfw",
}


def derive_rating(wd_rating_value: str | None) -> str:
    """Map a WD rating-head value to the schema rating; unknown -> 'unrated'."""
    key = (wd_rating_value or "").strip().lower()
    return WD_RATING_TO_SCHEMA.get(key, "unrated")


def select_unprocessed_images(
    conn: sqlite3.Connection,
    count: int,
    person: str | None = None,
) -> list[tuple]:
    """Return up to ``count`` (id, path, filename, person) rows with processed=0.

    Ordered by id (deterministic, restart-safe). Optional person filter scopes
    the pass (used for priority/per-person runs).
    """
    sql = "SELECT id, path, filename, person FROM images WHERE processed = 0"
    params: list = []
    if person:
        sql += " AND person = ?"
        params.append(person)
    sql += " ORDER BY id LIMIT ?"
    params.append(count)
    return conn.execute(sql, params).fetchall()


def clear_tier0_tags(session: Session, image_id: int) -> int:
    """Delete an image's Tier-0 (wd_eva02 + joytag) tag rows. Returns row count.

    Called before a re-tag so a lowered/raised threshold or schema change
    produces a clean, uniform tag set (no stale sub-threshold rows survive).
    Leaves non-Tier-0 rows (e.g. user/vlm) untouched.
    """
    return (
        session.query(Tag)
        .filter(Tag.image_id == image_id, Tag.tag_source.in_(TIER0_SOURCES))
        .delete(synchronize_session=False)
    )


def _assign_rating_label(session: Session, image_id: int, value: str) -> None:
    """Assign the single-select Rating LABEL (Wave 2c — images.rating dropped).

    No-op when the label tables (migration 013) are absent. Single-select:
    delete any prior Rating row for this image first, then insert. ``unrated`` is
    the absence of a Rating label, so it just clears any existing assignment.
    """
    from sqlalchemy import text

    has_tables = session.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='label_sets'")
    ).first()
    if has_tables is None:
        return
    present = session.execute(
        text("SELECT id FROM label_sets WHERE name = 'Rating'")
    ).first()
    if present is None:
        return
    set_id = int(present[0])
    session.execute(
        text("DELETE FROM user_labels WHERE image_id = :iid AND set_id = :sid"),
        {"iid": image_id, "sid": set_id},
    )
    if value and value != "unrated":
        session.execute(
            text(
                "INSERT OR IGNORE INTO user_labels "
                "(image_id, set_id, category, value, owner_id) "
                "VALUES (:iid, :sid, 'Rating', :val, 1)"
            ),
            {"iid": image_id, "sid": set_id, "val": value},
        )


def finalize_image(
    session: Session,
    image_id: int,
    wd_rating_value: str | None = None,
) -> None:
    """Mark an image processed; set its rating from the WD rating head if given.

    Rating is the Rating LABEL set now (Wave 2c — images.rating column dropped):
    a derived rating is written as a single-select Rating label assignment, not a
    column. A None rating value sets processed=1 without touching the existing
    Rating label (so a Tier-3-only pass never blanks a previously-derived rating).
    """
    session.query(Image).filter(Image.id == image_id).update(
        {"processed": True}, synchronize_session=False
    )
    if wd_rating_value is not None:
        _assign_rating_label(session, image_id, derive_rating(wd_rating_value))


def extract_wd_rating(rows: list[dict]) -> str | None:
    """Pull the WD rating value out of Tier-0 scored rows (category == 'rating')."""
    for row in rows:
        if row.get("category") == "rating":
            return row.get("value")
    return None
