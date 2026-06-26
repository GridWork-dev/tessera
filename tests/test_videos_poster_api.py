"""Tests for the poster_locked field + manual-pick PATCH endpoint (Wave 2a).

Route handlers read ``webui.deps.db`` at request time; we monkeypatch it onto a
seeded temp DB. The real ffmpeg regen path is monkeypatched out so the test is
hermetic (no ffmpeg / no real video needed).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pipeline.database import Video
from webui import deps, routes_videos
from webui.main import app

client = TestClient(app)


@pytest.fixture
def video_corpus(db, monkeypatch):
    monkeypatch.setattr(deps, "db", db)
    with db.get_session() as s:
        s.add(
            Video(
                id=1,
                path="v/a.mp4",
                filename="a.mp4",
                file_hash="vh1",
                duration=42.0,
                poster_path="cache/posters/vh1.jpg",
                poster_locked=0,
                processed=1,
            )
        )
        s.commit()
    return db


def test_detail_includes_poster_locked(video_corpus):
    r = client.get("/api/videos/1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "poster_locked" in body
    assert body["poster_locked"] is False


def test_patch_sets_locked_flag(video_corpus):
    r = client.patch("/api/videos/1/poster", json={"locked": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["video_id"] == 1
    assert body["poster_locked"] is True
    # GET detail now reflects the locked flag.
    assert client.get("/api/videos/1").json()["poster_locked"] is True


def test_patch_timestamp_regenerates_and_locks(video_corpus, monkeypatch):
    calls: list[float] = []

    def fake_generate_poster(path, out_path, *, seek=10.0, duration=None, **kw):
        calls.append(seek)
        return True

    monkeypatch.setattr(routes_videos, "generate_poster", fake_generate_poster)
    r = client.patch("/api/videos/1/poster", json={"timestamp": 12.5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["poster_locked"] is True
    assert calls == [12.5]  # regenerated at the requested timestamp


def test_patch_unknown_video_404(video_corpus):
    r = client.patch("/api/videos/999/poster", json={"locked": True})
    assert r.status_code == 404


def test_patch_empty_body_422(video_corpus):
    # Wave 2a review nit: a PATCH with neither timestamp nor locked is a no-op
    # client error — must 422 rather than silently returning 200 with no change.
    r = client.patch("/api/videos/1/poster", json={})
    assert r.status_code == 422


def test_video_sort_rejects_unknown_value(video_corpus):
    # Wave 2a review nit: an unknown sort must 422 (mirrors /api/search), not
    # silently fall through to 'recent'.
    r = client.get("/api/videos", params={"sort": "bogus"})
    assert r.status_code == 422
    # A valid sort still works.
    assert client.get("/api/videos", params={"sort": "duration"}).status_code == 200
