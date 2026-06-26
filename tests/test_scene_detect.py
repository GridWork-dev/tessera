"""
Tests for pipeline/scene_detect.py — real PySceneDetect AdaptiveDetector on a
tiny synthesized clip, persisted into a temp DB. Skips cleanly when scenedetect
(or its ffmpeg-synthesized input) is unavailable. The real library is never
touched.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipeline.database import Database, Video, VideoScene

# scenedetect is lazy-imported inside the module's functions; guard detection
# tests so collection still succeeds when it (or opencv) is absent.
pytest.importorskip("scenedetect")

from pipeline.scene_detect import (  # noqa: E402
    detect_and_persist,
    detect_scenes,
    has_scenes,
    persist_scenes,
)

FFMPEG = "ffmpeg"


def _synth_clip(out: Path, *, duration: int = 4, size: str = "320x240") -> None:
    """Synthesize a tiny clip whose content shifts so a cut is detectable."""
    cmd = [
        FFMPEG,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={duration}:size={size}:rate=10",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-shortest",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        pytest.skip(f"ffmpeg could not synthesize a test clip: {result.stderr[:300]}")


@pytest.fixture
def clip(tmp_path: Path) -> Path:
    out = tmp_path / "clip.mp4"
    _synth_clip(out)
    return out


def _make_video(db: Database) -> int:
    with db.get_session() as s:
        v = Video(path="library/x/videos/clip.mp4", file_hash="hash1", processed=1)
        s.add(v)
        s.commit()
        return v.id


def test_detect_scenes_returns_list(clip: Path):
    scenes = detect_scenes(clip)
    assert isinstance(scenes, list)
    assert len(scenes) >= 1
    for start, end in scenes:
        assert isinstance(start, float)
        assert isinstance(end, float)
        assert end >= start


def test_persist_scenes_writes_rows(tmp_path: Path, clip: Path):
    db = Database(str(tmp_path / "catalog.db"))
    video_id = _make_video(db)
    scenes = detect_scenes(clip)

    written = persist_scenes(db, video_id, scenes)
    assert written == len(scenes)
    with db.get_session() as s:
        rows = (
            s.query(VideoScene)
            .filter(VideoScene.video_id == video_id)
            .order_by(VideoScene.scene_index)
            .all()
        )
        assert len(rows) == len(scenes)
        assert [r.scene_index for r in rows] == list(range(len(scenes)))
        assert all(r.processed == 0 for r in rows)


def test_persist_scenes_idempotent(tmp_path: Path):
    db = Database(str(tmp_path / "catalog.db"))
    video_id = _make_video(db)
    scenes = [(0.0, 2.0), (2.0, 4.0)]

    persist_scenes(db, video_id, scenes)
    persist_scenes(db, video_id, scenes)  # re-run must not duplicate
    with db.get_session() as s:
        assert s.query(VideoScene).filter(
            VideoScene.video_id == video_id
        ).count() == len(scenes)


def test_detect_and_persist_resume_skips(tmp_path: Path):
    db = Database(str(tmp_path / "catalog.db"))
    video_id = _make_video(db)
    persist_scenes(db, video_id, [(0.0, 1.0)])
    assert has_scenes(db, video_id) is True
    # Already has scenes -> detect_and_persist must skip (return 0), no re-detect.
    assert detect_and_persist(db, video_id, tmp_path / "nonexistent.mp4") == 0
    with db.get_session() as s:
        assert s.query(VideoScene).filter(VideoScene.video_id == video_id).count() == 1
