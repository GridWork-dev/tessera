"""
Tests for pipeline/video_sprites.py — real ffmpeg sprite generation on a tiny
synthesized clip + WebVTT cue correctness. The #1-bug guard (cue interval ==
sampling interval) is asserted explicitly. The real library is never touched.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from pipeline.video_sprites import (
    create_sprite_sheet,
    format_timestamp,
    write_webvtt,
)

FFMPEG = "ffmpeg"
_CUE_RE = re.compile(r"(\d\d:\d\d:\d\d\.\d\d\d)\s+-->\s+(\d\d:\d\d:\d\d\.\d\d\d)")


def _synth_clip(out: Path, *, duration: int = 4, size: str = "320x240") -> None:
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
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        pytest.skip("ffmpeg not installed")
    if result.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        pytest.skip(f"ffmpeg could not synthesize a test clip: {result.stderr[:300]}")


@pytest.fixture
def clip(tmp_path: Path) -> Path:
    out = tmp_path / "clip.mp4"
    _synth_clip(out)
    return out


def _ts_to_seconds(ts: str) -> float:
    h, m, rest = ts.split(":")
    s, ms = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def test_format_timestamp():
    assert format_timestamp(0) == "00:00:00.000"
    assert format_timestamp(2.0) == "00:00:02.000"
    assert format_timestamp(3661.5) == "01:01:01.500"


def test_create_sprite_sheet(clip: Path, tmp_path: Path):
    out = tmp_path / "sprite.jpg"
    interval = 2.0
    meta = create_sprite_sheet(clip, out, interval=interval, cols=5, tile_w=160)

    assert out.exists() and out.stat().st_size > 0
    assert meta["sprite_path"] == str(out)
    assert meta["interval"] == interval
    assert meta["cols"] == 5
    assert meta["tile_w"] == 160
    # 4s / 2s interval -> 2 sampled frames.
    assert meta["count"] == 2
    assert meta["rows"] >= 1
    assert meta["tile_h"] > 0


def test_write_webvtt_cue_interval_matches_sampling_interval(tmp_path: Path):
    """THE #1-bug guard: cue spacing MUST equal the sprite sampling interval."""
    vtt = tmp_path / "scrub.vtt"
    interval = 2.0
    count = 3
    write_webvtt(
        vtt,
        sprite_url="sprite.jpg",
        interval=interval,
        cols=5,
        tile_w=160,
        tile_h=90,
        count=count,
    )

    text = vtt.read_text(encoding="utf-8")
    assert text.startswith("WEBVTT")

    cues = _CUE_RE.findall(text)
    assert len(cues) == count  # one cue per sampled frame

    # First cue ends exactly at the sampling interval.
    first_start, first_end = cues[0]
    assert _ts_to_seconds(first_start) == pytest.approx(0.0)
    assert _ts_to_seconds(first_end) == pytest.approx(interval)

    # EVERY cue's duration equals the sampling interval (the guard).
    for start, end in cues:
        assert _ts_to_seconds(end) - _ts_to_seconds(start) == pytest.approx(interval)

    # Cue i starts at i*interval — cue spacing == sampling interval.
    for i, (start, _end) in enumerate(cues):
        assert _ts_to_seconds(start) == pytest.approx(i * interval)


def test_write_webvtt_xywh_regions(tmp_path: Path):
    vtt = tmp_path / "scrub.vtt"
    write_webvtt(
        vtt,
        sprite_url="sprite.jpg",
        interval=2.0,
        cols=2,
        tile_w=160,
        tile_h=90,
        count=3,
    )
    text = vtt.read_text(encoding="utf-8")
    # tile 0 -> (0,0); tile 1 -> (160,0); tile 2 wraps to row 1 -> (0,90).
    assert "sprite.jpg#xywh=0,0,160,90" in text
    assert "sprite.jpg#xywh=160,0,160,90" in text
    assert "sprite.jpg#xywh=0,90,160,90" in text


def test_sprite_and_vtt_end_to_end(clip: Path, tmp_path: Path):
    sprite = tmp_path / "sprite.jpg"
    vtt = tmp_path / "scrub.vtt"
    meta = create_sprite_sheet(clip, sprite, interval=2.0, cols=5, tile_w=160)
    write_webvtt(
        vtt,
        sprite_url=sprite.name,
        interval=meta["interval"],
        cols=meta["cols"],
        tile_w=meta["tile_w"],
        tile_h=meta["tile_h"],
        count=meta["count"],
    )
    cues = _CUE_RE.findall(vtt.read_text(encoding="utf-8"))
    # cue count == sampled-frame count.
    assert len(cues) == meta["count"]
    # first cue end == sampling interval.
    _start, end = cues[0]
    assert _ts_to_seconds(end) == pytest.approx(meta["interval"])
