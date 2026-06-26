"""Resumable backfill driver — every scene of every video through the seam.

Walks ``videos`` -> ``video_scenes`` and, per scene, runs ``process_scene``
(keyframe -> embed/tag/caption/detect via the dispatcher). Per VIDEO it runs
Whisper ONCE over the whole clip and distributes the segments to scenes (one
decode, many scenes — far cheaper than per-scene audio decodes).

Resumable + drop-resilient, matching ``pipeline/video_ingest``: a scene already
``processed=1`` is skipped; any per-scene failure is logged and the loop
CONTINUES (never aborts the whole run). The single writer is one sqlite-vec
connection (so the scene vec table works); the caller's ``Database`` provides the
ORM read side.

This is a BUILD artifact: the full 264-clip run is a GPU-playbook job, not invoked
here. The per-video path is also what ``webui/routes_video_deep.py`` triggers.
"""

from __future__ import annotations

import logging

from pipeline.database import Database, Video, VideoScene
from pipeline.paths import resolve_image_path
from pipeline.video_deep.scene_pipeline import DEFAULT_CAPS, process_scene
from pipeline.video_deep.transcribe import (
    persist_scene_transcript,
    segments_for_scene,
    transcribe_audio,
)

logger = logging.getLogger(__name__)


def _open_writer(db: Database):
    """One raw sqlite-vec connection — the single writer for scene-level rows."""
    from pipeline.tier1_embedder import open_vec_db  # lazy (pulls sqlite-vec)

    return open_vec_db(db.db_path)


def _transcribe_video(conn, db: Database, video, scenes, *, model_size: str) -> int:
    """Transcribe one clip once + distribute segments to its scenes.

    Returns the total number of transcript rows written. Best-effort: a clip with
    no audio (or a transcription error) writes nothing and does not abort.
    """
    if not video.has_audio or not video.path:
        return 0
    video_abs = resolve_image_path(video.path)
    if not video_abs.exists():
        return 0
    try:
        segments = transcribe_audio(video_abs, model_size=model_size)
    except Exception as exc:  # noqa: BLE001 - best-effort; never abort the run
        logger.warning("transcription failed for video %s: %s", video.id, exc)
        return 0

    model = f"faster-whisper:{model_size}"
    total = 0
    for scene in scenes:
        window = segments_for_scene(
            segments, scene.start_time or 0.0, scene.end_time or 0.0
        )
        total += persist_scene_transcript(conn, scene.id, window, model=model)
    return total


def backfill_videos(
    db: Database,
    dispatcher,
    *,
    limit: int | None = None,
    caps=DEFAULT_CAPS,
    uncensored: bool = True,
    transcribe: bool = True,
    whisper_model_size: str = "base",
    video_id: int | None = None,
) -> dict:
    """Backfill deep-video enrichment over videos' scenes. Returns counts.

    ``limit`` bounds the number of VIDEOS processed (resume-skips don't count).
    ``video_id`` restricts the run to one video (the per-video API trigger).
    ``caps`` selects which capabilities to run; ``transcribe`` toggles Whisper.

    Resumable: scenes already ``processed=1`` are skipped. Per-scene/per-video
    failures are logged and skipped — the loop never raises.
    """
    counts = {"videos": 0, "scenes": 0, "skipped": 0, "errors": 0, "transcript_rows": 0}
    conn = _open_writer(db)
    session = db.get_session()
    try:
        vq = session.query(Video).filter(Video.processed != -1)
        if video_id is not None:
            vq = vq.filter(Video.id == video_id)
        for video in vq.order_by(Video.id).all():
            if limit is not None and counts["videos"] >= limit:
                break
            scenes = (
                session.query(VideoScene)
                .filter(VideoScene.video_id == video.id)
                .order_by(VideoScene.scene_index)
                .all()
            )
            if not scenes:
                continue
            counts["videos"] += 1

            if transcribe:
                counts["transcript_rows"] += _transcribe_video(
                    conn, db, video, scenes, model_size=whisper_model_size
                )

            for scene in scenes:
                try:
                    res = process_scene(
                        conn,
                        dispatcher,
                        scene,
                        video,
                        caps=caps,
                        uncensored=uncensored,
                    )
                    if res.get("skipped"):
                        counts["skipped"] += 1
                    else:
                        counts["scenes"] += 1
                    conn.commit()
                except Exception as exc:  # noqa: BLE001 - drop-resilient
                    conn.rollback()
                    logger.warning("scene %s failed: %s", scene.id, exc)
                    counts["errors"] += 1
        conn.commit()
    finally:
        session.close()
        conn.close()

    logger.info(
        "deep-video backfill: %d videos, %d scenes, %d skipped, %d errors, %d "
        "transcript rows",
        counts["videos"],
        counts["scenes"],
        counts["skipped"],
        counts["errors"],
        counts["transcript_rows"],
    )
    return counts
