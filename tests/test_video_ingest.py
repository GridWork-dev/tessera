"""
Tests for pipeline/video_ingest.py — real ffprobe/ffmpeg on a tiny synthesized
clip; the real library is NEVER touched (everything lives under tmp_path, and
the content root is monkeypatched to tmp_path).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import pipeline.paths as paths
from pipeline.database import Database, Video
from pipeline.video_ingest import (
    generate_poster,
    ingest_videos,
    orientation,
    probe_video,
)

FFMPEG = "ffmpeg"


def _synth_clip(out: Path, *, duration: int = 4, size: str = "320x240") -> None:
    """Synthesize a tiny H.264 + audio clip with ffmpeg; skip if unavailable."""
    cmd = [
        FFMPEG,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={duration}:size={size}:rate=10",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=1000:duration={duration}",
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


def test_orientation():
    assert orientation(320, 240) == "landscape"
    assert orientation(240, 320) == "portrait"
    assert orientation(200, 200) == "square"
    assert orientation(None, None) == "landscape"


def test_probe_video(clip: Path):
    meta = probe_video(clip)
    assert meta["duration"] == pytest.approx(4.0, abs=0.5)
    assert meta["width"] == 320
    assert meta["height"] == 240
    assert meta["has_audio"] == 1
    assert meta["codec"]  # set (h264)
    assert meta["filesize"] > 0
    assert orientation(meta["width"], meta["height"]) == "landscape"
    assert meta["fps"] == pytest.approx(10.0, abs=0.5)


def test_generate_poster(clip: Path, tmp_path: Path):
    out = tmp_path / "posters" / "poster.jpg"
    # duration (~4s) < default seek (10s) -> -ss omitted, still yields a frame.
    ok = generate_poster(clip, out, duration=4.0)
    assert ok is True
    assert out.exists() and out.stat().st_size > 0


def test_ingest_videos_inserts_one_relative_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Point the content root at tmp_path so stored paths are relative + portable.
    monkeypatch.setattr(paths, "content_root", lambda: tmp_path)

    lib = tmp_path / "library" / "alice" / "videos"
    lib.mkdir(parents=True)
    _synth_clip(lib / "clip.mp4")

    db = Database(str(tmp_path / "catalog.db"))
    counts = ingest_videos(db, tmp_path)

    assert counts == {"added": 1, "skipped": 0, "quarantined": 0}
    with db.get_session() as s:
        rows = s.query(Video).all()
        assert len(rows) == 1
        v = rows[0]
        assert v.processed == 1
        assert not os.path.isabs(v.path)
        assert v.path == "library/alice/videos/clip.mp4"
        assert v.person == "alice"
        assert v.media_type == "video"
        assert v.duration == pytest.approx(4.0, abs=0.5)
        assert v.width == 320 and v.height == 240
        assert v.has_audio == 1
        # poster stored relative.
        assert v.poster_path and not os.path.isabs(v.poster_path)
        assert (tmp_path / v.poster_path).exists()


def test_ingest_videos_resume_skips_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(paths, "content_root", lambda: tmp_path)
    lib = tmp_path / "library" / "bob" / "videos"
    lib.mkdir(parents=True)
    _synth_clip(lib / "clip.mp4")

    db = Database(str(tmp_path / "catalog.db"))
    first = ingest_videos(db, tmp_path)
    assert first["added"] == 1
    second = ingest_videos(db, tmp_path)
    assert second == {"added": 0, "skipped": 1, "quarantined": 0}
    with db.get_session() as s:
        assert s.query(Video).count() == 1


def test_ingest_videos_quarantines_corrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(paths, "content_root", lambda: tmp_path)
    lib = tmp_path / "library" / "carol" / "videos"
    lib.mkdir(parents=True)
    (lib / "broken.mp4").write_bytes(os.urandom(2048))  # random bytes, not a video

    db = Database(str(tmp_path / "catalog.db"))
    # Must NOT raise out of the loop.
    counts = ingest_videos(db, tmp_path)

    assert counts["quarantined"] == 1
    assert counts["added"] == 0
    with db.get_session() as s:
        rows = s.query(Video).all()
        assert len(rows) == 1
        assert rows[0].processed == -1
        assert rows[0].path == "library/carol/videos/broken.mp4"
