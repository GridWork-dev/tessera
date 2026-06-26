"""Video pillar (D1/D5) list / facets / detail / asset-serving routes.

Videos live in the SEPARATE ``videos`` table (approved design 2026-06-23), not
as ``images`` rows. The fully-unified images+videos grid is a D-pillar
follow-up (it needs the search.py owner_type work, gated on the H100 run), so
for now videos get their own list/facets/serve surface that the frontend
renders as a video-card variant. With 0 videos ingested these return empty/404
gracefully — the schema + serving are ready for when ingest runs.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func

from pipeline.database import Video, VideoScene
from pipeline.paths import resolve_image_path
from pipeline.video_ingest import generate_poster
from webui import deps
from webui import search as search_svc
from webui.scoping import can_view, scope_query

router = APIRouter()

VALID_VIDEO_SORTS = ("recent", "random", "filename", "size", "duration")

DURATION_BUCKETS = (
    ("<30s", 0.0, 30.0),
    ("30s-2m", 30.0, 120.0),
    ("2m-10m", 120.0, 600.0),
    ("10m+", 600.0, float("inf")),
)


def _duration_bucket(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    for label, lo, hi in DURATION_BUCKETS:
        if lo <= seconds < hi:
            return label
    return None


def _orientation(width: int | None, height: int | None) -> str | None:
    if not width or not height:
        return None
    if width > height:
        return "landscape"
    if height > width:
        return "portrait"
    return "square"


def _video_card(v: Video) -> dict:
    """Serialize a Video row to the card shape the frontend grid consumes."""
    return {
        "id": v.id,
        "file_hash": v.file_hash,
        "filename": v.filename,
        "person": v.person,
        "width": v.width,
        "height": v.height,
        "duration": v.duration,
        "duration_bucket": _duration_bucket(v.duration),
        "orientation": _orientation(v.width, v.height),
        "fps": v.fps,
        "codec": v.codec,
        "has_audio": bool(v.has_audio),
        "rating": v.rating,
        "media_type": "video",
        "processed": v.processed,
        "has_poster": bool(v.poster_path),
        "has_sprite": bool(v.sprite_path),
        "poster_locked": bool(v.poster_locked),
    }


@router.get("/api/videos")
async def api_videos_list(
    request: Request,
    person: str = Query(None),
    rating: str = Query(None),
    label: list[str] = Query(None),
    orientation: str = Query(None),
    duration: str = Query(None, description="bucket label: <30s|30s-2m|2m-10m|10m+"),
    has_audio: bool = Query(None),
    processed: int = Query(None),
    sort: str = Query("recent"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    """List videos (separate `videos` table) with facet-aligned filters."""
    # Wave 2a nit: reject an unknown sort (mirrors /api/search) instead of
    # silently falling through to recent.
    if sort not in VALID_VIDEO_SORTS:
        raise HTTPException(
            status_code=422, detail=f"sort must be one of {VALID_VIDEO_SORTS}"
        )
    session = deps.db.get_session()
    try:
        query = session.query(Video)
        if person:
            query = query.filter(Video.person == person)
        # Generic label filter (Wave 2b), keyed on user_labels.image_id == Video.id
        # (the assignment table is id-generic). AND across sets / OR within a set.
        label_filter = search_svc.parse_labels(label)
        if label_filter and search_svc._label_tables_present(session):
            for idx, (set_name, values) in enumerate(label_filter.items()):
                query = query.filter(
                    Video.id.in_(
                        search_svc._label_match_subquery(
                            session, set_name, values, prefix=f"l{idx}"
                        )
                    )
                )
        if rating:
            clause = Video.rating == rating
            if search_svc._label_tables_present(session):
                clause = clause | Video.id.in_(
                    search_svc._label_match_subquery(
                        session, "Rating", [rating], prefix="rat"
                    )
                )
            query = query.filter(clause)
        if has_audio is not None:
            query = query.filter(Video.has_audio == (1 if has_audio else 0))
        if processed is not None:
            query = query.filter(Video.processed == processed)
        else:
            # Hide quarantined (processed == -1) clips by default — they have no
            # usable metadata/poster and would render as broken cards.
            query = query.filter(Video.processed != -1)
        if duration:
            match = next((b for b in DURATION_BUCKETS if b[0] == duration), None)
            if match:
                _, lo, hi = match
                query = query.filter(Video.duration >= lo)
                if hi != float("inf"):
                    query = query.filter(Video.duration < hi)
        if orientation in ("portrait", "landscape", "square"):
            # Orientation is derived (not a column); express it in SQL over w/h.
            if orientation == "landscape":
                query = query.filter(Video.width > Video.height)
            elif orientation == "portrait":
                query = query.filter(Video.height > Video.width)
            else:
                query = query.filter(Video.width == Video.height)

        # Per-user row scoping (audit C1) — no-op for admin / auth-off.
        query = scope_query(query, Video, request)

        # Video sort keys (Wave 2a). No date/relevance for videos; unknown ->
        # recent (imported_at desc).
        if sort == "random":
            query = query.order_by(func.random())
        elif sort == "filename":
            query = query.order_by(Video.filename.asc(), Video.id.asc())
        elif sort == "size":
            query = query.order_by(Video.filesize.desc(), Video.id.desc())
        elif sort == "duration":
            query = query.order_by(Video.duration.desc(), Video.id.desc())
        else:  # recent / unknown
            query = query.order_by(Video.imported_at.desc(), Video.id.desc())

        total = query.count()
        offset = (page - 1) * limit
        videos = query.offset(offset).limit(limit).all()
        return {
            "videos": [_video_card(v) for v in videos],
            "total": total,
            "page": page,
            "total_pages": max(1, (total + limit - 1) // limit),
            "label_facets": search_svc.compute_video_label_facets(deps.db),
        }
    finally:
        session.close()


@router.get("/api/videos/facets")
async def api_videos_facets(request: Request):
    """Video facet counts: duration bucket / orientation / has-audio / people /
    ratings. Global counts over all videos (disjunctive refinement is a
    follow-up once a real corpus exists)."""
    session = deps.db.get_session()
    try:
        facet_q = scope_query(  # no-op for admin / auth-off (audit C1)
            session.query(
                Video.duration,
                Video.width,
                Video.height,
                Video.has_audio,
                Video.person,
                Video.rating,
            ),
            Video,
            request,
        )
        rows = facet_q.all()
        duration: dict[str, int] = {}
        orientation: dict[str, int] = {}
        has_audio: dict[str, int] = {"yes": 0, "no": 0}
        people: dict[str, int] = {}
        ratings: dict[str, int] = {}
        for dur, w, h, audio, person, rating in rows:
            if (b := _duration_bucket(dur)) is not None:
                duration[b] = duration.get(b, 0) + 1
            if (o := _orientation(w, h)) is not None:
                orientation[o] = orientation.get(o, 0) + 1
            has_audio["yes" if audio else "no"] += 1
            if person:
                people[person] = people.get(person, 0) + 1
            if rating:
                ratings[rating] = ratings.get(rating, 0) + 1
        return {
            "duration": duration,
            "orientation": orientation,
            "has_audio": has_audio,
            "people": people,
            "ratings": ratings,
        }
    finally:
        session.close()


@router.get("/api/videos/{video_id}")
async def api_video_detail(video_id: int, request: Request):
    """Full video detail incl. detected scenes (empty until D2 runs)."""
    session = deps.db.get_session()
    try:
        v = session.query(Video).filter(Video.id == video_id).first()
        # Cross-tenant fetch reads as not-found (audit C1; no-op admin/auth-off).
        if not v or not can_view(v, request):
            raise HTTPException(status_code=404, detail="Video not found")
        scenes = (
            session.query(VideoScene)
            .filter(VideoScene.video_id == video_id)
            .order_by(VideoScene.scene_index)
            .all()
        )
        card = _video_card(v)
        card.update(
            {
                "path": v.path,
                "directory": v.directory,
                "bitrate": v.bitrate,
                "filesize": v.filesize,
                "scenes": [
                    {
                        "scene_index": s.scene_index,
                        "start_time": s.start_time,
                        "end_time": s.end_time,
                        "caption": s.caption,
                    }
                    for s in scenes
                ],
            }
        )
        return card
    finally:
        session.close()


@router.patch("/api/videos/{video_id}/poster")
async def api_video_poster_patch(
    video_id: int,
    request: Request,
    timestamp: float | None = Body(default=None),
    locked: bool | None = Body(default=None),
):
    """Manual poster pick + lock (Wave 2a).

    ``timestamp`` (seconds) regenerates the poster at that frame and locks it
    (a deliberate pick is always protected from auto re-selection). ``locked``
    alone just toggles the flag. At least one must be provided.
    """
    # Wave 2a nit: an empty body (neither field) is a no-op client error -> 422.
    if timestamp is None and locked is None:
        raise HTTPException(
            status_code=422, detail="provide at least one of: timestamp, locked"
        )
    session = deps.db.get_session()
    try:
        v = session.query(Video).filter(Video.id == video_id).first()
        if not v or not can_view(v, request):
            raise HTTPException(status_code=404, detail="Video not found")

        if timestamp is not None and v.path and v.poster_path:
            src = resolve_image_path(v.path)
            out = resolve_image_path(v.poster_path)
            generate_poster(src, out, seek=float(timestamp), duration=v.duration)
            v.poster_locked = 1
        elif locked is not None:
            v.poster_locked = 1 if locked else 0
        session.commit()
        return {
            "ok": True,
            "video_id": video_id,
            "poster_locked": bool(v.poster_locked),
        }
    finally:
        session.close()


def _serve_video_asset(file_hash: str, attr: str, media_type: str):
    """Resolve a video row by hash and FileResponse one of its asset paths.

    ``attr`` is the Video column holding a content-relative path
    (poster_path/sprite_path/vtt_path/path). 404 if the row, the path, or the
    file is missing — never leaks an absolute path in the error.
    """
    session = deps.db.get_session()
    try:
        v = session.query(Video).filter(Video.file_hash == file_hash).first()
        if not v:
            raise HTTPException(status_code=404, detail="Video not found")
        rel = getattr(v, attr, None)
        if not rel:
            raise HTTPException(status_code=404, detail="Asset not available")
        path = resolve_image_path(rel)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Asset file not found")
        return FileResponse(path, media_type=media_type)
    finally:
        session.close()


@router.get("/media/video-poster/{file_hash}")
async def serve_video_poster(file_hash: str):
    """Serve a video's poster frame."""
    return _serve_video_asset(file_hash, "poster_path", "image/jpeg")


@router.get("/media/video-sprite/{file_hash}")
async def serve_video_sprite(file_hash: str):
    """Serve a video's scrub-sprite mosaic."""
    return _serve_video_asset(file_hash, "sprite_path", "image/jpeg")


@router.get("/media/video-vtt/{file_hash}")
async def serve_video_vtt(file_hash: str):
    """Serve a video's WebVTT scrub cue map."""
    return _serve_video_asset(file_hash, "vtt_path", "text/vtt")


@router.get("/media/video/{file_hash}")
async def serve_video_file(file_hash: str):
    """Stream the video file itself (FileResponse honors Range for seeking)."""
    _VIDEO_CT = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".m4v": "video/mp4",
        ".avi": "video/x-msvideo",
    }
    session = deps.db.get_session()
    try:
        v = session.query(Video).filter(Video.file_hash == file_hash).first()
        if not v or not v.path:
            raise HTTPException(status_code=404, detail="Video not found")
        path = resolve_image_path(v.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")
        ct = _VIDEO_CT.get(path.suffix.lower(), "application/octet-stream")
        return FileResponse(path, media_type=ct)
    finally:
        session.close()
