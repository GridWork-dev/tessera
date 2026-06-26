"""Deep-video API — scene detail + per-video backfill trigger.

A NEW ``APIRouter`` (NOT registered — the orchestrator adds the
``include_router`` line in ``webui/main.py``; see the lane report). All endpoints
are read-only except the backfill trigger, which kicks the resumable driver onto
a FastAPI ``BackgroundTasks`` so heavy work runs off the request thread.

The scene-level tables (``scene_captions`` / ``scene_transcripts`` /
``scene_faces``) are additive (migration 011) and have no ORM models yet, so we
read them with parameterized raw SQL through the ORM session's connection — the
same single source-of-truth DB.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import text

from pipeline.database import Database, Video, VideoScene
from webui.auth_routes import require_admin

router = APIRouter(prefix="/api/video-deep", tags=["video-deep"])


@lru_cache(maxsize=1)
def get_db() -> Database:
    """Lazily build the shared catalog Database (settings-driven path).

    Lazy (not module-level) so importing this router has NO side effects and no
    filesystem dependency — the module imports cleanly in tests / on a box
    without the real catalog.db. The app + endpoints get the same cached handle.
    """
    from pipeline.settings import settings

    return Database(str(settings.database_path))


def _scene_enrichment(session, scene_id: int) -> dict:
    """Read the additive scene-level rows for one scene (tags/caption/transcript)."""
    conn = session.connection()
    tags = [
        {"category": r[0], "value": r[1], "confidence": r[2], "tag_source": r[3]}
        for r in conn.execute(
            text(
                "SELECT category, value, confidence, tag_source FROM scene_tags "
                "WHERE scene_id = :sid ORDER BY confidence DESC"
            ),
            {"sid": scene_id},
        )
    ]
    captions = [
        {"model": r[0], "caption": r[1]}
        for r in conn.execute(
            text("SELECT model, caption FROM scene_captions WHERE scene_id = :sid"),
            {"sid": scene_id},
        )
    ]
    transcript = [
        {"start_time": r[0], "end_time": r[1], "text": r[2], "language": r[3]}
        for r in conn.execute(
            text(
                "SELECT start_time, end_time, text, language FROM scene_transcripts "
                "WHERE scene_id = :sid ORDER BY segment_index"
            ),
            {"sid": scene_id},
        )
    ]
    face_count = conn.execute(
        text("SELECT COUNT(*) FROM scene_faces WHERE scene_id = :sid"),
        {"sid": scene_id},
    ).scalar_one()
    return {
        "tags": tags,
        "captions": captions,
        "transcript": transcript,
        "transcript_text": " ".join(seg["text"] for seg in transcript),
        "face_count": face_count,
    }


@router.get("/scenes/{scene_id}")
async def scene_detail(scene_id: int):
    """Scene detail: the scene row + its tags, captions, transcript, face count."""
    session = get_db().get_session()
    try:
        scene = session.query(VideoScene).filter(VideoScene.id == scene_id).first()
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        out = {
            "id": scene.id,
            "video_id": scene.video_id,
            "scene_index": scene.scene_index,
            "start_time": scene.start_time,
            "end_time": scene.end_time,
            "keyframe_path": scene.keyframe_path,
            "caption": scene.caption,
            "processed": scene.processed,
        }
        out.update(_scene_enrichment(session, scene_id))
        return out
    finally:
        session.close()


@router.get("/videos/{video_id}/scenes")
async def video_scenes(video_id: int):
    """List a video's scenes with per-scene enrichment status flags."""
    session = get_db().get_session()
    try:
        video = session.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        scenes = (
            session.query(VideoScene)
            .filter(VideoScene.video_id == video_id)
            .order_by(VideoScene.scene_index)
            .all()
        )
        conn = session.connection()
        out = []
        for s in scenes:
            counts = conn.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM scene_tags WHERE scene_id = :sid), "
                    "(SELECT COUNT(*) FROM scene_captions WHERE scene_id = :sid), "
                    "(SELECT COUNT(*) FROM scene_transcripts WHERE scene_id = :sid), "
                    "(SELECT COUNT(*) FROM scene_faces WHERE scene_id = :sid)"
                ),
                {"sid": s.id},
            ).one()
            out.append(
                {
                    "id": s.id,
                    "scene_index": s.scene_index,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "keyframe_path": s.keyframe_path,
                    "processed": s.processed,
                    "tagged": counts[0] > 0,
                    "captioned": counts[1] > 0,
                    "transcribed": counts[2] > 0,
                    "face_count": counts[3],
                }
            )
        return {"video_id": video_id, "scenes": out}
    finally:
        session.close()


def _run_backfill(video_id: int) -> None:
    """Background task: enrich one video's scenes via the compute dispatcher."""
    from pipeline.compute.dispatcher import ComputeDispatcher
    from pipeline.video_deep.backfill import backfill_videos

    dispatcher = ComputeDispatcher.from_config()
    backfill_videos(get_db(), dispatcher, video_id=video_id)


@router.post("/videos/{video_id}/backfill")
async def trigger_backfill(
    video_id: int,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_admin),
):
    """Trigger deep enrichment for ONE video's scenes (runs in the background).

    Mutates the catalog (scene tags/captions/transcripts), so it requires an admin
    when auth is on AND an explicit apply flag — never an unguarded HTTP write
    (audit P1). The full 264-clip backfill is a GPU-playbook job; this is the
    per-video, on-demand trigger.
    """
    import os

    if os.environ.get("MEDIA_PIPELINE_BACKFILL_APPLY", "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        raise HTTPException(
            status_code=403,
            detail="deep-video backfill is gated; set "
            "MEDIA_PIPELINE_BACKFILL_APPLY=1 to enable",
        )
    session = get_db().get_session()
    try:
        video = session.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
    finally:
        session.close()
    background_tasks.add_task(_run_backfill, video_id)
    return {"status": "started", "video_id": video_id}
