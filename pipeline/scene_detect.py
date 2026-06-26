"""
Scene detection — PySceneDetect AdaptiveDetector -> ``video_scenes`` rows.

``scenedetect`` is imported lazily inside functions so the module (and its
pure-logic / persistence tests) import cleanly even when scenedetect is absent;
detection tests guard with ``pytest.importorskip``.

Resumable: a video that already has ``video_scenes`` rows is skipped, and
``persist_scenes`` is idempotent (it clears existing scenes for the video first),
so a re-run never duplicates.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .database import Database, VideoScene

logger = logging.getLogger(__name__)


def detect_scenes(
    video_path: Path | str,
    adaptive_threshold: float = 3.0,
    min_scene_len: int = 15,
) -> list[tuple[float, float]]:
    """Detect scenes in a video -> list of ``(start_sec, end_sec)`` tuples.

    Uses scenedetect's v0.7 ``AdaptiveDetector`` (the default detector) via a
    ``SceneManager``, then ``get_scene_list(start_in_scene=True)`` so a video
    with NO hard cuts still yields one whole-clip scene (the bare ``detect()``
    helper returns ``[]`` in that case). ``FrameTimecode`` boundaries are
    converted to seconds via ``get_seconds()``. A readable video therefore always
    yields at least one scene.
    """
    from scenedetect import (  # lazy heavy import
        AdaptiveDetector,
        SceneManager,
        open_video,
    )

    video = open_video(str(video_path))
    scene_manager = SceneManager()
    scene_manager.add_detector(
        AdaptiveDetector(
            adaptive_threshold=adaptive_threshold, min_scene_len=min_scene_len
        )
    )
    scene_manager.detect_scenes(video)
    # start_in_scene=True -> an uncut clip becomes a single (0, duration) scene.
    scene_list = scene_manager.get_scene_list(start_in_scene=True)
    return [(start.get_seconds(), end.get_seconds()) for start, end in scene_list]


def has_scenes(db: Database, video_id: int) -> bool:
    """True if the video already has any ``video_scenes`` rows (resume key)."""
    with db.get_session() as session:
        return (
            session.query(VideoScene).filter(VideoScene.video_id == video_id).first()
            is not None
        )


def persist_scenes(
    db: Database, video_id: int, scenes: list[tuple[float, float]]
) -> int:
    """Write ``VideoScene`` rows for a video; return the number written.

    Idempotent: existing scenes for ``video_id`` are deleted first, so re-running
    with the same (or a fresh) scene list never duplicates rows. Each row gets a
    sequential ``scene_index`` (0..n-1) and ``processed=0``.
    """
    written = 0
    with db.get_session() as session:
        session.query(VideoScene).filter(VideoScene.video_id == video_id).delete(
            synchronize_session=False
        )
        for index, (start, end) in enumerate(scenes):
            session.add(
                VideoScene(
                    video_id=video_id,
                    scene_index=index,
                    start_time=float(start),
                    end_time=float(end),
                    processed=0,
                )
            )
            written += 1
        session.commit()
    return written


def detect_and_persist(
    db: Database,
    video_id: int,
    video_path: Path | str,
    **detect_kwargs: Any,
) -> int:
    """Detect + persist scenes for one video, skipping if already done.

    Resumable: returns ``0`` without re-detecting when the video already has
    scenes. Otherwise detects and persists, returning the number of rows written.
    """
    if has_scenes(db, video_id):
        logger.debug("video %s already has scenes; skipping", video_id)
        return 0
    scenes = detect_scenes(video_path, **detect_kwargs)
    return persist_scenes(db, video_id, scenes)
