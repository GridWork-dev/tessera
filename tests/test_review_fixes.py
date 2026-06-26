"""
Regression tests for the 12 bugs surfaced by the adversarial review of the
next-phase diff. Each test locks one fix so it can't silently regress.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import pipeline.paths as paths
import webui.search as S
from pipeline.database import (
    Caption,
    Database,
    Image,
    ModelRun,
    record_model_run,
)

FFMPEG = "ffmpeg"


def _synth_clip(out: Path, duration: float = 4.0, size: str = "320x240") -> bool:
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
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and out.exists() and out.stat().st_size > 0


# --------------------------------------------------------------------------- #
# #8 — verify_self_retrieval: empty probe set must NOT vacuously pass GATE 0   #
# --------------------------------------------------------------------------- #


def test_classify_readiness_empty_probe_is_insufficient():
    from scripts.verify_self_retrieval import classify_readiness

    # Full corpus coverage but ZERO probes -> must be "insufficient", never "ready"
    assert classify_readiness(26590, 26590, 0, 0) == "insufficient"
    # Sanity: full coverage + all probes present -> ready
    assert classify_readiness(26590, 26590, 10, 10) == "ready"
    # Partial probe coverage -> insufficient
    assert classify_readiness(26590, 26590, 9, 10) == "insufficient"
    # Low vector coverage -> insufficient (today's real state)
    assert classify_readiness(65, 26590, 10, 10) == "insufficient"


def test_run_gate_zero_probes_is_not_a_pass():
    from scripts.verify_self_retrieval import run_gate

    report = run_gate("data/catalog.db", [], 0.99)
    assert report["checked"] == 0
    assert report["pass"] is False  # checked>0 required for a pass


# --------------------------------------------------------------------------- #
# #10 — record_model_run idempotency with an identifier-less manifest          #
# --------------------------------------------------------------------------- #


def test_record_model_run_empty_manifest_idempotent():
    db = Database(":memory:")
    with db.get_session() as s:
        a = record_model_run(s, {})
        s.commit()
        b = record_model_run(s, {})
        s.commit()
        assert a.id == b.id
        assert s.query(ModelRun).count() == 1
        assert a.run_key and a.run_key.startswith("auto:")


def test_record_model_run_tier_kwarg_in_key():
    db = Database(":memory:")
    with db.get_session() as s:
        a = record_model_run(s, {}, tier="tier0")
        s.commit()
        b = record_model_run(s, {}, tier="tier0")
        s.commit()
        assert a.id == b.id
        assert s.query(ModelRun).count() == 1


# --------------------------------------------------------------------------- #
# #9 — _caption_fts degrades to [] when the FTS table is absent (no raise)     #
# --------------------------------------------------------------------------- #


def test_caption_fts_missing_table_returns_empty():
    db = Database(":memory:")  # create_all does NOT build the captions_fts vtable
    with db.get_session() as s:
        img = Image(path="a.webp", file_hash="h")
        s.add(img)
        s.flush()
        s.add(Caption(image_id=img.id, model="m", caption="a red car"))
        s.commit()
        # Must NOT raise OperationalError: no such table: captions_fts
        assert S._caption_fts(s, "red car", None) == []


# --------------------------------------------------------------------------- #
# #6 — generate_poster succeeds when duration == seek (strict >, not >=)       #
# --------------------------------------------------------------------------- #


def test_generate_poster_at_exact_seek_duration(tmp_path):
    from pipeline.video_ingest import generate_poster

    clip = tmp_path / "c.mp4"
    if not _synth_clip(clip, duration=4.0):
        pytest.skip("ffmpeg could not synthesize a clip")
    out = tmp_path / "poster.jpg"
    # duration == seek would previously seek to EOF and produce nothing.
    assert generate_poster(clip, out, duration=4.0, seek=4.0) is True
    assert out.exists() and out.stat().st_size > 0


# --------------------------------------------------------------------------- #
# #2 / #5 — sprite count matches ffmpeg (round, not ceil) + sub-interval none  #
# --------------------------------------------------------------------------- #


def test_sprite_count_rounds_not_ceils(tmp_path):
    from pipeline.video_sprites import create_sprite_sheet

    clip = tmp_path / "c.mp4"
    if not _synth_clip(clip, duration=5.0):
        pytest.skip("ffmpeg could not synthesize a clip")
    # duration 4.5 @ interval 2: ffmpeg emits round(2.25)=2 frames; ceil would be 3.
    meta = create_sprite_sheet(
        clip, tmp_path / "sprite.jpg", interval=2.0, duration=4.5
    )
    assert meta["count"] == 2
    assert meta["sprite_path"] is not None
    assert Path(meta["sprite_path"]).exists()


def test_sprite_sub_interval_yields_no_sheet(tmp_path):
    from pipeline.video_sprites import create_sprite_sheet

    clip = tmp_path / "c.mp4"
    if not _synth_clip(clip, duration=4.0):
        pytest.skip("ffmpeg could not synthesize a clip")
    # duration 0.4 @ interval 2: ffmpeg's fps filter emits 0 frames -> no sheet.
    meta = create_sprite_sheet(clip, tmp_path / "s.jpg", interval=2.0, duration=0.4)
    assert meta["count"] == 0
    assert meta["sprite_path"] is None


# --------------------------------------------------------------------------- #
# #1 — ingest_videos quarantines an unreadable file instead of crashing        #
# --------------------------------------------------------------------------- #


def test_ingest_quarantines_unreadable_file(tmp_path, monkeypatch):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root can read 0o000 files; chmod guard is a no-op")
    from pipeline.video_ingest import ingest_videos

    monkeypatch.setattr(paths, "content_root", lambda: tmp_path)
    clip = tmp_path / "v.mp4"
    if not _synth_clip(clip, duration=2.0):
        pytest.skip("ffmpeg could not synthesize a clip")
    os.chmod(clip, 0o000)
    db = Database(str(tmp_path / "c.db"))
    try:
        # Must NOT raise — the unreadable file is quarantined, the walk continues.
        counts = ingest_videos(db, tmp_path)
    finally:
        os.chmod(clip, 0o644)  # restore so tmp cleanup works
    assert counts["quarantined"] >= 1
    assert counts["added"] == 0
