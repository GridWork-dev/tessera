"""Image list / detail / flag / rating / notes / user-label routes."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Form, HTTPException, Query, Request
from sqlalchemy import and_, exists, func, or_, select, text
from sqlalchemy.orm import joinedload

from pipeline.database import Embedding, ExclusionRule, Image, Notes, Tag
from pipeline.paths import content_root, relative_to_content, resolve_image_path
from webui import deps
from webui import search as search_svc
from webui.scoping import can_view, scope_query, viewer_owner_id

router = APIRouter()


@router.get("/api/images")
async def api_images_list(
    request: Request,
    person: str = Query(None),
    category: str = Query(None),
    value: str = Query(None),
    tags: list[str] = Query(None),
    rating: str = Query(None),
    label: list[str] = Query(None),
    processed: bool = Query(None),
    flagged: bool = Query(None),
    collection_id: int = Query(None),
    q: str = Query(None),
    sort: str = Query("recent"),
    exclude: bool = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    """List images with filters, pagination, and sort.

    ``collection_id`` filters to a collection's members via a server-side
    subquery JOIN on ``collection_items`` (NOT a client id-list — SQLite caps
    host params and a large literal IN defeats the planner). Composes with every
    other filter + sort; the returned order is the standard /api/images order,
    NOT collection_items.sort_order (manual reorder is out of scope).
    """
    session = deps.db.get_session()
    try:
        query = session.query(Image).options(joinedload(Image.tags))

        if person:
            query = query.filter(Image.person == person)
        if collection_id is not None:
            query = query.filter(
                Image.id.in_(
                    select(deps.collection_items_t.c.image_id).where(
                        deps.collection_items_t.c.collection_id == collection_id
                    )
                )
            )
        if category and value:
            query = query.filter(
                Image.id.in_(
                    session.query(Tag.image_id).filter(
                        Tag.category == category, Tag.value == value
                    )
                )
            )
        # Multi-tag AND: each "category:value" spec further narrows the set
        # (intersection across categories — "blonde AND outdoor AND smiling").
        if tags:
            for spec in tags:
                cat, sep, val = spec.partition(":")
                if not sep or not cat or not val:
                    continue
                query = query.filter(
                    Image.id.in_(
                        session.query(Tag.image_id).filter(
                            Tag.category == cat, Tag.value == val
                        )
                    )
                )
        # Generic label filter (Wave 2b): ``label=<set>:<value>`` (repeatable),
        # AND across sets / OR within a set, over user_labels joined to label_sets.
        label_filter = search_svc.parse_labels(label)
        query = search_svc._apply_label_filter(query, session, label_filter)

        # Legacy ``rating=`` is equivalent to ``label=Rating:<value>`` (spec 3.5);
        # it filters purely on the Rating label set now — the images.rating column
        # was dropped in Wave 2c. No-op when the label tables are absent.
        if rating and search_svc._label_tables_present(session):
            query = query.filter(
                Image.id.in_(
                    search_svc._label_match_subquery(
                        session, "Rating", [rating], prefix="rat"
                    )
                )
            )
        if processed is not None:
            query = query.filter(Image.processed == processed)
        if flagged is not None:
            query = query.filter(Image.flagged == flagged)
        if q:
            query = (
                query.join(Tag)
                .filter(or_(Tag.value.ilike(f"%{q}%"), Image.person.ilike(f"%{q}%")))
                .distinct()
            )

        # Exclusion filter: exclude images with tags matching any enabled rule
        if exclude:
            excluded_subq = (
                select(Tag.id)
                .join(
                    ExclusionRule,
                    and_(
                        Tag.category == ExclusionRule.category,
                        Tag.value == ExclusionRule.value,
                    ),
                )
                .where(
                    Tag.image_id == Image.id,
                    ExclusionRule.enabled.is_(True),
                )
            )
            query = query.filter(~exists(excluded_subq))

        # Per-user row scoping (audit C1): a non-admin viewer sees own + legacy
        # un-owned (NULL) rows. No-op for admin / auth-off (this deployment).
        query = scope_query(query, Image, request)

        # Sorting (Wave 2a sort keys). Unknown values fall through to recent.
        if sort == "random":
            query = query.order_by(func.random())
        elif sort == "created":
            query = query.order_by(Image.created_at.desc(), Image.id.desc())
        elif sort == "modified":
            query = query.order_by(Image.modified_at.desc(), Image.id.desc())
        elif sort == "filename":
            query = query.order_by(Image.filename.asc(), Image.id.asc())
        elif sort == "size":
            query = query.order_by(Image.filesize.desc(), Image.id.desc())
        else:  # recent / relevance / unknown
            query = query.order_by(Image.imported_at.desc(), Image.id.desc())

        total = query.count()
        offset = (page - 1) * limit
        images = query.offset(offset).limit(limit).all()

        # Rating is the Rating label set now (Wave 2c) — the images.rating column
        # was dropped. Source the human rating per image from user_labels.
        ratings = search_svc.rating_map_for_ids(session, [img.id for img in images])

        return {
            "images": [
                {
                    "id": img.id,
                    "file_hash": img.file_hash,
                    "filename": img.filename,
                    "person": img.person,
                    "width": img.width,
                    "height": img.height,
                    "rating": ratings.get(img.id),
                    "processed": img.processed,
                    "flagged": bool(img.flagged),
                    "flag_action": img.flag_action,
                    "tags": [
                        {
                            "category": t.category,
                            "value": t.value,
                            "confidence": t.confidence,
                        }
                        for t in img.tags
                    ],
                }
                for img in images
            ],
            "total": total,
            "page": page,
            "total_pages": max(1, (total + limit - 1) // limit),
            "label_facets": search_svc.compute_label_facets(
                deps.db,
                labels=label,
                rating=rating,
                person=person,
                viewer_owner_id=viewer_owner_id(request),
            ),
        }
    finally:
        session.close()


@router.get("/api/images/{image_id}")
async def get_image_detail(image_id: int, request: Request):
    """Full-detail single image for the in-depth inspector — one round trip.

    Combines all image columns + tags + notes + captions + parsed nudenet_regions
    + embedding/similarity availability booleans. 404 if the id is unknown. Never
    leaks absolute paths: ``path`` stays relative to content root (the same value
    stored in the DB); the inspector resolves media via ``file_hash`` like the
    grid does. ``captions`` is empty until Tier 2 lands; ``has_embedding`` /
    ``similar_available`` are false until Tier 1 vectors are populated.
    """
    session = deps.db.get_session()
    try:
        image = (
            session.query(Image)
            .options(
                joinedload(Image.tags),
                joinedload(Image.notes),
                joinedload(Image.captions),
            )
            .filter(Image.id == image_id)
            .first()
        )
        # Scope to the viewer: a row they can't see reads as not-found, not 403
        # (don't reveal existence). No-op for admin / auth-off (audit C1).
        if not image or not can_view(image, request):
            raise HTTPException(status_code=404, detail="Image not found")

        # NudeNet regions: stored as a JSON array string (Tier 3). Parse defensively
        # — a malformed/empty value degrades to None rather than 500-ing the view.
        nudenet_regions = None
        if image.nudenet_regions:
            try:
                nudenet_regions = json.loads(image.nudenet_regions)
            except ValueError, TypeError:
                nudenet_regions = None

        # has_embedding: this image has a row in the schema embeddings table.
        # similar_available: any vectors exist in the sqlite-vec rescore index
        # (matches the /similar endpoint's degradation contract — global, not
        # per-image, so the UI knows whether the feature is usable at all).
        has_embedding = (
            session.query(Embedding).filter(Embedding.image_id == image_id).count() > 0
        )
        similar_available = search_svc.vector_count(deps.db) > 0

        notes_content = image.notes[0].content if image.notes else None

        # Human rating from the Rating label set (Wave 2c — column dropped).
        rating_value = search_svc.rating_map_for_ids(session, [image.id]).get(image.id)

        return {
            "id": image.id,
            "path": image.path,
            "filename": image.filename,
            "directory": image.directory,
            "person": image.person,
            "file_hash": image.file_hash,
            "width": image.width,
            "height": image.height,
            "filesize": image.filesize,
            "format": image.format,
            "created_at": str(image.created_at) if image.created_at else None,
            "modified_at": str(image.modified_at) if image.modified_at else None,
            "imported_at": str(image.imported_at) if image.imported_at else None,
            "media_type": image.media_type,
            "rating": rating_value,
            "processed": bool(image.processed),
            "flagged": bool(image.flagged),
            "flag_action": image.flag_action,
            "original_path": image.original_path,
            "original_filename": image.original_filename,
            "has_metadata": bool(image.has_metadata),
            "has_thumbnail": bool(image.has_thumbnail),
            "tags": [
                {
                    "category": t.category,
                    "value": t.value,
                    "confidence": t.confidence,
                    "tag_source": t.tag_source,
                }
                for t in image.tags
            ],
            "notes": notes_content,
            "captions": [
                {"model": c.model, "caption": c.caption} for c in image.captions
            ],
            "nudenet_regions": nudenet_regions,
            "has_embedding": has_embedding,
            "similar_available": similar_available,
        }
    finally:
        session.close()


def _apply_flag(session, image_id: int, action: str) -> dict:
    """Apply a single flag to one image (shared by single + batch flag routes).

    Mirrors the single ``/flag`` route exactly: marks the image flagged, sets the
    action, and on ``reject`` moves the source file under ``content/_rejected/``
    (stored back as a relative path). Does NOT commit — the caller owns the
    transaction so a batch is one atomic commit. Returns a per-id result dict;
    ``ok=False`` when the image id is unknown (so batch can report partials).
    """
    import shutil

    image = session.query(Image).filter(Image.id == image_id).first()
    if not image:
        return {"id": image_id, "ok": False, "error": "not found"}

    image.flagged = True
    image.flag_action = action

    if action == "reject":
        src = resolve_image_path(image.path)
        if src.exists():
            rejected_dir = content_root() / "_rejected"
            rejected_dir.mkdir(parents=True, exist_ok=True)
            dst = rejected_dir / src.name
            if dst.exists():
                hash_suffix = (image.file_hash or src.stem)[:8]
                dst = rejected_dir / (src.stem + "_" + hash_suffix + src.suffix)
            shutil.move(str(src), str(dst))
            image.path = relative_to_content(dst)

    return {"id": image_id, "ok": True, "action": action}


# NOTE: the batch route MUST be registered before the single-flag route below.
# FastAPI matches in registration order; with ``/api/images/{image_id}/flag``
# first, a request to ``/api/images/batch/flag`` would bind image_id="batch" and
# 422 on the int converter before reaching the batch handler.
@router.post("/api/images/batch/flag")
async def batch_flag_images(payload: dict):
    """Bulk triage: flag many images with the same action in one transaction.

    Body: ``{"image_ids": [int, ...], "action": "reject"|"maybe"|"keep"}``.
    Reuses the SAME per-id flag logic as the single ``/flag`` route (``_apply_flag``)
    so reject still moves files and stores relative paths. Unknown ids are reported
    in ``results`` with ``ok=False`` rather than failing the whole batch.
    """
    image_ids = payload.get("image_ids")
    action = payload.get("action")

    if not isinstance(image_ids, list) or not all(
        isinstance(i, int) for i in image_ids
    ):
        raise HTTPException(
            status_code=400, detail="image_ids must be a list of integers"
        )
    if action not in ("reject", "maybe", "keep"):
        raise HTTPException(
            status_code=400, detail="action must be reject, maybe, or keep"
        )

    session = deps.db.get_session()
    try:
        results = [_apply_flag(session, iid, action) for iid in image_ids]
        session.commit()
        updated = sum(1 for r in results if r["ok"])
        return {"ok": True, "updated": updated, "results": results}
    finally:
        session.close()


@router.post("/api/images/{image_id}/flag")
async def flag_image(image_id: int, action: str = Form(...)):
    """Flag an image: reject (move file + mark), maybe, keep."""
    if action not in ("reject", "maybe", "keep"):
        raise HTTPException(
            status_code=400, detail="action must be reject, maybe, or keep"
        )

    session = deps.db.get_session()
    try:
        result = _apply_flag(session, image_id, action)
        if not result["ok"]:
            raise HTTPException(status_code=404, detail="Image not found")
        session.commit()
        return {"ok": True, "action": action}
    finally:
        session.close()


RATING_VALUES = ("unrated", "sfw", "suggestive", "nsfw")


@router.post("/api/images/{image_id}/rating")
async def set_image_rating(image_id: int, value: str = Form(...)):
    """Canonical rating-set endpoint: assigns the Rating LABEL set (Wave 2c).

    Rating is now the single-select ``Rating`` label set in ``user_labels`` — the
    images.rating column was dropped. Browse/search/stats read it back via
    ``search.rating_map_for_ids``. Form-encoded POST matches the house single-field
    mutation convention (/flag, /notes). Validates against RATING_VALUES; 404 on
    unknown id. Single-select semantics (one rating per image) are enforced by
    ``LabelStore.assign_label``.
    """
    if value not in RATING_VALUES:
        raise HTTPException(
            status_code=400, detail=f"rating must be one of {RATING_VALUES}"
        )
    session = deps.db.get_session()
    try:
        image = session.query(Image).filter(Image.id == image_id).first()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        row = session.execute(
            text("SELECT id FROM label_sets WHERE name = 'Rating'")
        ).first()
        if row is None:
            raise HTTPException(status_code=500, detail="Rating label set missing")
        rating_set_id = int(row[0])
    finally:
        session.close()

    from pipeline.labels.store import LabelStore

    LabelStore(deps.db.db_path).assign_label(image_id, rating_set_id, value)
    return {"ok": True, "rating": value}


# --- Notes routes ---


@router.post("/api/images/{image_id}/notes")
async def save_notes(image_id: int, content: str = Form(...)):
    """Save creative planning notes for an image."""
    session = deps.db.get_session()
    try:
        image = session.query(Image).filter(Image.id == image_id).first()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")

        # Upsert: update existing or create new
        note = session.query(Notes).filter(Notes.image_id == image_id).first()
        if note:
            note.content = content
            note.updated_at = datetime.now()
        else:
            note = Notes(image_id=image_id, content=content)
            session.add(note)

        session.commit()

        return {
            "id": note.id,
            "image_id": note.image_id,
            "content": note.content,
            "created_at": str(note.created_at) if note.created_at else None,
            "updated_at": str(note.updated_at) if note.updated_at else None,
        }
    finally:
        session.close()


@router.get("/api/images/{image_id}/notes")
async def get_notes(image_id: int):
    """Get creative planning notes for an image."""
    session = deps.db.get_session()
    try:
        note = session.query(Notes).filter(Notes.image_id == image_id).first()
        if not note:
            raise HTTPException(status_code=404, detail="No notes found")

        return {
            "id": note.id,
            "image_id": note.image_id,
            "content": note.content,
            "created_at": str(note.created_at) if note.created_at else None,
            "updated_at": str(note.updated_at) if note.updated_at else None,
        }
    finally:
        session.close()


# --- User labels routes (user_labels table from migration 002; no model — raw
# SQL like collections). Manual, user-authored labels distinct from the
# model-generated `tags` table. ---


@router.get("/api/images/{image_id}/labels")
async def get_user_labels(image_id: int):
    """List manual (free-form) user labels for an image (newest first).

    Only free-form labels (``set_id IS NULL``) — set-based assignments like the
    Rating label set (Wave 2c) are managed via the label-sets API, not this
    legacy CRUD, so they must not leak in here.
    """
    session = deps.db.get_session()
    try:
        rows = session.execute(
            text(
                "SELECT id, category, value, created_at FROM user_labels "
                "WHERE image_id = :iid AND set_id IS NULL ORDER BY id DESC"
            ),
            {"iid": image_id},
        ).fetchall()
        return {
            "labels": [
                {
                    "id": r[0],
                    "category": r[1],
                    "value": r[2],
                    "created_at": r[3],
                }
                for r in rows
            ]
        }
    finally:
        session.close()


@router.post("/api/images/{image_id}/labels")
async def add_user_label(
    image_id: int, value: str = Form(...), category: str = Form("user")
):
    """Add a manual user label to an image. Idempotent on (image_id, category, value)."""
    session = deps.db.get_session()
    try:
        image = session.query(Image).filter(Image.id == image_id).first()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")

        session.execute(
            text(
                "INSERT OR IGNORE INTO user_labels (image_id, category, value) "
                "VALUES (:iid, :cat, :val)"
            ),
            {"iid": image_id, "cat": category, "val": value},
        )
        session.commit()

        row = session.execute(
            text(
                "SELECT id, category, value, created_at FROM user_labels "
                "WHERE image_id = :iid AND category = :cat AND value = :val"
            ),
            {"iid": image_id, "cat": category, "val": value},
        ).fetchone()
        return {
            "id": row[0],
            "image_id": image_id,
            "category": row[1],
            "value": row[2],
            "created_at": row[3],
        }
    finally:
        session.close()


@router.delete("/api/images/{image_id}/labels/{label_id}")
async def delete_user_label(image_id: int, label_id: int):
    """Delete a manual user label by id (scoped to the image)."""
    session = deps.db.get_session()
    try:
        session.execute(
            text("DELETE FROM user_labels WHERE id = :lid AND image_id = :iid"),
            {"lid": label_id, "iid": image_id},
        )
        session.commit()
        return {"ok": True, "id": label_id}
    finally:
        session.close()
