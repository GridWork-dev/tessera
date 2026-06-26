"""Per-scene keyframe extraction.

A scene keyframe is the single representative frame the compute seam runs over
(embed/tag/caption/detect). We seek to the scene MIDPOINT — robust against the
fade-in/black frames common at scene starts — and write a JPEG under the content
root, then store its RELATIVE path on ``video_scenes.keyframe_path``.

Idempotent / resumable: ``ensure_scene_keyframe`` skips a scene whose keyframe is
already recorded and present on disk. ffmpeg is invoked via the same thin
``subprocess`` wrapper style as ``pipeline/video_ingest.py``; the module imports
cheaply (no heavy deps at top).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from pipeline.paths import content_root, relative_to_content, resolve_image_path

logger = logging.getLogger(__name__)

# Bare name (on PATH); matches pipeline/video_ingest.py.
FFMPEG = "ffmpeg"

# Where scene keyframes live, relative to the content root.
KEYFRAME_SUBDIR = "_scene_keyframes"


def scene_keyframe_time(start: float, end: float) -> float:
    """Pick the representative timestamp for a scene -> its MIDPOINT (seconds).

    Midpoint dodges the leading black/fade frames a scene-start seek would catch.
    A degenerate/zero-length scene falls back to ``start``.
    """
    if end <= start:
        return float(start)
    return float(start) + (float(end) - float(start)) / 2.0


def extract_keyframe(
    video_path: Path | str,
    timestamp: float,
    out_path: Path | str,
    scale_w: int = 512,
) -> bool:
    """Write a single frame at ``timestamp`` (s) from ``video_path`` to ``out_path``.

    ``ffmpeg -ss <t> -i <video> -frames:v 1 -vf scale=<w>:-2 <out>``. Creates the
    parent directory. Returns ``True`` iff ``out_path`` exists and is non-empty.
    Never raises on ffmpeg failure (caller treats a falsey return as a skip).
    """
    video_path = Path(video_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        FFMPEG,
        "-y",
        "-ss",
        str(max(0.0, float(timestamp))),
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-vf",
        f"scale={scale_w}:-2",
        str(out_path),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:  # ffmpeg missing / not executable
        logger.warning("ffmpeg keyframe extraction failed for %s: %s", video_path, exc)
        return False
    return out_path.exists() and out_path.stat().st_size > 0


def ensure_scene_keyframe(
    scene, video, *, keyframe_root: Path | None = None
) -> str | None:
    """Ensure a scene has a keyframe on disk; return its RELATIVE path (or None).

    Resumable: if ``scene.keyframe_path`` is set and the file exists, returns it
    unchanged. Otherwise extracts a frame at the scene midpoint, names it
    ``<video.file_hash[:12]>_<scene_index>.jpg`` under ``KEYFRAME_SUBDIR``, and
    returns the new relative path (the caller persists it on the scene row).

    ``scene`` and ``video`` are ORM rows (duck-typed: ``.start_time``/``.end_time``/
    ``.scene_index``/``.keyframe_path`` and ``.path``/``.file_hash``). Returns
    ``None`` when extraction fails.
    """
    if scene.keyframe_path:
        existing = resolve_image_path(scene.keyframe_path)
        if existing.exists():
            return scene.keyframe_path

    if not video.path:
        return None
    video_abs = resolve_image_path(video.path)
    if not video_abs.exists():
        logger.warning("video file missing for scene keyframe: %s", video.path)
        return None

    root = (
        keyframe_root if keyframe_root is not None else content_root() / KEYFRAME_SUBDIR
    )
    stem = (video.file_hash or "video")[:12]
    out_abs = root / f"{stem}_{scene.scene_index}.jpg"
    t = scene_keyframe_time(scene.start_time or 0.0, scene.end_time or 0.0)
    if not extract_keyframe(video_abs, t, out_abs):
        return None
    return relative_to_content(out_abs)
