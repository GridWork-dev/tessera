"""Deep video layer — per-scene enrichment through the compute seam.

Lane C of the platform-evolution build. Takes each detected video scene's
KEYFRAME through all four compute capabilities (embed/tag/caption/detect) by
REUSING ``pipeline/compute`` (no new inference code), adds Whisper audio
transcription, and emits a per-scene face-detect hand-off for the faces lane.

Everything here is import-cheap: heavy deps (ffmpeg subprocess, faster-whisper,
the dispatcher's backend models, sqlite-vec) are invoked lazily / behind the
seam, so this package and its pure-logic tests import on a box without weights.
See ``docs/superpowers/specs/2026-06-24-deep-video-design.md``.
"""

from __future__ import annotations

from pipeline.video_deep.backfill import backfill_videos
from pipeline.video_deep.keyframe import (
    ensure_scene_keyframe,
    extract_keyframe,
    scene_keyframe_time,
)
from pipeline.video_deep.scene_faces import (
    crop_face,
    detect_scene_faces,
    persist_scene_faces,
)
from pipeline.video_deep.scene_pipeline import process_scene
from pipeline.video_deep.transcribe import (
    TranscriptSegment,
    persist_scene_transcript,
    segments_for_scene,
    transcribe_audio,
)
from pipeline.video_deep.vec_scene import (
    VEC_SCENE_TABLE,
    ensure_scene_vec_table,
    register_vec_owner,
    upsert_scene_vec,
)

__all__ = [
    "VEC_SCENE_TABLE",
    "TranscriptSegment",
    "backfill_videos",
    "crop_face",
    "detect_scene_faces",
    "ensure_scene_keyframe",
    "ensure_scene_vec_table",
    "extract_keyframe",
    "persist_scene_faces",
    "persist_scene_transcript",
    "process_scene",
    "register_vec_owner",
    "scene_keyframe_time",
    "segments_for_scene",
    "transcribe_audio",
    "upsert_scene_vec",
]
