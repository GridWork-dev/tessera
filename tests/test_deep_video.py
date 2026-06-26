"""Tests for Lane C — deep video layer (pipeline/video_deep + migration 011).

Pure-logic + persistence tests run with NO torch, NO whisper, NO network: a
fresh TEMP sqlite db gets migration 011 (plus the migration-006 prerequisite
tables it keys to) applied, and a FAKE compute dispatcher drives the scene
pipeline. Heavy/optional deps (faster-whisper, torch via the real backends) are
guarded with ``pytest.importorskip`` / ``skipif`` and never touched here.

Mirrors tests/test_self_retrieval.py: the repo root is inserted on sys.path FIRST
so the worktree's code (not any installed copy) is exercised. The real
data/catalog.db is NEVER touched — every test builds its own temp db.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.compute.base import (  # noqa: E402
    Capability,
    Caption,
    Regions,
    TagSet,
    Vector,
)
from pipeline.video_deep.keyframe import scene_keyframe_time  # noqa: E402
from pipeline.video_deep.scene_faces import detect_scene_faces  # noqa: E402
from pipeline.video_deep.transcribe import (  # noqa: E402
    TranscriptSegment,
    persist_scene_transcript,
    segments_for_scene,
)

REPO_ROOT = Path(__file__).parent.parent
MIGRATION_011 = REPO_ROOT / "data" / "migrations" / "011_video_deep.sql"

# Migration-006 prerequisite tables that 011 keys to. We create only what 011
# references (NOT the whole of 006) so the temp schema stays minimal + the real
# DB is never involved.
PREREQ_SQL = """
CREATE TABLE videos (id INTEGER PRIMARY KEY, path TEXT, file_hash TEXT,
    has_audio INTEGER DEFAULT 0, processed INTEGER DEFAULT 0);
CREATE TABLE video_scenes (id INTEGER PRIMARY KEY, video_id INTEGER,
    scene_index INTEGER, start_time REAL, end_time REAL, keyframe_path TEXT,
    caption TEXT, processed INTEGER DEFAULT 0);
CREATE TABLE scene_tags (id INTEGER PRIMARY KEY, scene_id INTEGER, category TEXT,
    value TEXT, confidence REAL, tag_source TEXT);
CREATE TABLE vec_owner (vec_id INTEGER PRIMARY KEY, owner_type TEXT, owner_id INTEGER);
CREATE TABLE model_runs (id INTEGER PRIMARY KEY, run_key TEXT);
"""


@pytest.fixture
def conn(tmp_path):
    """A temp sqlite db with the 006-prereq tables + migration 011 applied."""
    db_file = tmp_path / "test_catalog.db"
    c = sqlite3.connect(str(db_file))
    c.executescript(PREREQ_SQL)
    c.executescript(MIGRATION_011.read_text())
    c.commit()
    yield c
    c.close()


# --------------------------------------------------------------------------- #
# Migration 011 — additive tables exist with the expected columns.            #
# --------------------------------------------------------------------------- #
def test_migration_creates_scene_tables(conn):
    names = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"scene_captions", "scene_transcripts", "scene_faces"} <= names


def test_scene_captions_unique_on_scene_model(conn):
    conn.execute(
        "INSERT INTO scene_captions (scene_id, model, caption) VALUES (1, 'm', 'a')"
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO scene_captions (scene_id, model, caption) VALUES (1, 'm', 'b')"
        )


# --------------------------------------------------------------------------- #
# keyframe.scene_keyframe_time — pure midpoint selection.                      #
# --------------------------------------------------------------------------- #
def test_keyframe_time_is_midpoint():
    assert scene_keyframe_time(10.0, 20.0) == 15.0


def test_keyframe_time_degenerate_falls_back_to_start():
    assert scene_keyframe_time(5.0, 5.0) == 5.0
    assert scene_keyframe_time(8.0, 3.0) == 8.0


# --------------------------------------------------------------------------- #
# transcribe.segments_for_scene — pure window clipping by midpoint.           #
# --------------------------------------------------------------------------- #
def _seg(s, e, t="x"):
    return TranscriptSegment(start=s, end=e, text=t)


def test_segments_for_scene_keeps_overlapping_by_midpoint():
    segs = [_seg(0, 2, "a"), _seg(2, 4, "b"), _seg(4, 6, "c")]
    # window [2,4): only segment "b" (midpoint 3.0) lands inside.
    kept = segments_for_scene(segs, 2.0, 4.0)
    assert [s.text for s in kept] == ["b"]


def test_segments_for_scene_straddling_cue_lands_in_one_scene():
    # A cue [1,5] straddling the cut at 3: midpoint 3.0 -> belongs to [3,6), not [0,3).
    cue = _seg(1, 5, "straddle")
    assert segments_for_scene([cue], 0.0, 3.0) == []
    assert segments_for_scene([cue], 3.0, 6.0) == [cue]


def test_segments_for_scene_no_overlap_empty():
    assert segments_for_scene([_seg(10, 12)], 0.0, 5.0) == []


# --------------------------------------------------------------------------- #
# scene_faces.detect_scene_faces — pure face-label filter over Regions.       #
# --------------------------------------------------------------------------- #
def test_detect_scene_faces_filters_face_labels():
    regions = [
        {"label": "FACE_F", "score": 0.9, "box": [0, 0, 10, 10]},
        {"label": "BELLY", "score": 0.8, "box": [1, 1, 2, 2]},
        {"label": "face", "score": 0.7, "box": [3, 3, 4, 4]},
        {"label": "FACE_M", "score": 0.6},  # no box -> dropped
    ]
    faces = detect_scene_faces(regions)
    assert [f["label"] for f in faces] == ["FACE_F", "face"]


# --------------------------------------------------------------------------- #
# transcribe.persist_scene_transcript — idempotent raw-SQL write.             #
# --------------------------------------------------------------------------- #
def test_persist_scene_transcript_is_idempotent(conn):
    segs = [_seg(0, 1, "hello"), _seg(1, 2, "world")]
    n = persist_scene_transcript(conn, 7, segs, model="faster-whisper:base")
    conn.commit()
    assert n == 2
    # Re-run replaces, never duplicates.
    persist_scene_transcript(conn, 7, [_seg(0, 1, "again")], model="m")
    conn.commit()
    rows = conn.execute(
        "SELECT text FROM scene_transcripts WHERE scene_id = 7 ORDER BY segment_index"
    ).fetchall()
    assert [r[0] for r in rows] == ["again"]


# --------------------------------------------------------------------------- #
# vec_scene — scene vector + vec_owner population (no sqlite-vec extension     #
# needed for the vec_owner map; the float vec table needs the extension so it  #
# is exercised separately under a skipif).                                     #
# --------------------------------------------------------------------------- #
def test_register_vec_owner_maps_scene(conn):
    from pipeline.video_deep.vec_scene import register_vec_owner

    register_vec_owner(conn, 42)
    conn.commit()
    row = conn.execute(
        "SELECT owner_type, owner_id FROM vec_owner WHERE vec_id = 42"
    ).fetchone()
    assert row == ("scene", 42)
    # Idempotent (INSERT OR REPLACE) — re-run does not raise or duplicate.
    register_vec_owner(conn, 42)
    conn.commit()
    assert (
        conn.execute("SELECT COUNT(*) FROM vec_owner WHERE vec_id = 42").fetchone()[0]
        == 1
    )


# --------------------------------------------------------------------------- #
# scene_pipeline.process_scene — full drive via a FAKE dispatcher (no models). #
# --------------------------------------------------------------------------- #
class _FakeDispatcher:
    """Returns canned per-capability results; records privacy-gate usage."""

    def __init__(self):
        self.calls = []

    def run(self, cap, refs, *, uncensored=False):
        self.calls.append((cap, uncensored))
        if cap == Capability.EMBED:
            return [Vector(image_id=None, values=[0.1] * 1152, dim=1152, model="fake")]
        if cap == Capability.TAG:
            return [
                TagSet(
                    image_id=None,
                    tags=[
                        {
                            "category": "tags",
                            "value": "beach",
                            "confidence": 0.9,
                            "tag_source": "fake",
                        }
                    ],
                )
            ]
        if cap == Capability.CAPTION:
            return [Caption(image_id=None, text="a fake scene", model="fake")]
        if cap == Capability.DETECT:
            return [
                Regions(
                    image_id=None,
                    regions=[{"label": "face", "score": 0.9, "box": [0, 0, 4, 4]}],
                )
            ]
        raise AssertionError(cap)


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_process_scene_tag_caption_paths(conn, monkeypatch):
    """TAG + CAPTION run through the pipeline and persist (no keyframe I/O,
    no sqlite-vec extension): we stub the keyframe extractor and skip EMBED/DETECT."""
    from pipeline.video_deep import scene_pipeline

    # Stub keyframe extraction so no ffmpeg/file is needed.
    monkeypatch.setattr(
        scene_pipeline, "ensure_scene_keyframe", lambda scene, video: "kf/rel.jpg"
    )
    conn.execute(
        "INSERT INTO video_scenes (id, video_id, scene_index, start_time, end_time, "
        "processed) VALUES (3, 1, 0, 0.0, 5.0, 0)"
    )
    conn.commit()

    scene = _Row(
        id=3,
        scene_index=0,
        start_time=0.0,
        end_time=5.0,
        keyframe_path=None,
        processed=0,
    )
    video = _Row(id=1, path="lib/v.mp4", file_hash="abc123def456", has_audio=1)
    disp = _FakeDispatcher()

    summary = scene_pipeline.process_scene(
        conn,
        disp,
        scene,
        video,
        caps=(Capability.TAG, Capability.CAPTION),
        uncensored=True,
    )
    conn.commit()

    assert summary["tags"] == 1
    assert summary["captioned"] is True
    # Privacy gate flag propagated to every dispatcher call.
    assert all(uncensored for _cap, uncensored in disp.calls)
    # Persisted rows.
    assert (
        conn.execute("SELECT value FROM scene_tags WHERE scene_id=3").fetchone()[0]
        == "beach"
    )
    assert (
        conn.execute("SELECT caption FROM scene_captions WHERE scene_id=3").fetchone()[
            0
        ]
        == "a fake scene"
    )
    # Scene marked processed + keyframe path persisted + caption mirrored.
    row = conn.execute(
        "SELECT processed, keyframe_path, caption FROM video_scenes WHERE id=3"
    ).fetchone()
    assert row == (1, "kf/rel.jpg", "a fake scene")


def test_process_scene_skips_when_processed(conn):
    from pipeline.video_deep import scene_pipeline

    scene = _Row(
        id=9,
        scene_index=0,
        start_time=0.0,
        end_time=1.0,
        keyframe_path=None,
        processed=1,
    )
    video = _Row(id=1, path="lib/v.mp4", file_hash="x", has_audio=0)
    res = scene_pipeline.process_scene(conn, _FakeDispatcher(), scene, video)
    assert res["skipped"] is True


# --------------------------------------------------------------------------- #
# Optional: faster-whisper transcription smoke (guarded — dep absent on Mac).  #
# --------------------------------------------------------------------------- #
def test_transcribe_audio_requires_dep():
    """Without faster-whisper, transcribe_audio raises a clear install hint."""
    try:
        import faster_whisper  # noqa: F401

        pytest.skip("faster-whisper IS installed; absence-path not exercised here")
    except ImportError:
        from pipeline.video_deep.transcribe import transcribe_audio

        with pytest.raises(RuntimeError, match="faster-whisper not installed"):
            transcribe_audio("/nonexistent.mp4")
