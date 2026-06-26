"""Tests for Wave 2a sort keys (migration 014 + image/video ORDER BY branches).

All against TEMP sqlite DBs / the ``db`` fixture — never the live catalog.db.
No torch / no network.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline import migrations
from pipeline.database import Image, Video
from pipeline.settings import REPO_ROOT
from webui import deps
from webui.main import app

MIG_014 = REPO_ROOT / "data" / "migrations" / "014_sort_indexes.sql"

client = TestClient(app)


# --------------------------------------------------------------------------- #
# Task A1 — migration 014 creates the covering sort indexes (idempotently).    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def temp_sort_db(tmp_path):
    """A temp DB with bare images + videos tables holding the sort columns."""
    db = tmp_path / "sort.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE images (
            id INTEGER PRIMARY KEY, filename TEXT, filesize INTEGER,
            created_at TEXT, modified_at TEXT, imported_at TEXT
        );
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY, filename TEXT, filesize INTEGER,
            duration REAL, imported_at TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    return db


def _indexes(db: Path, like: str) -> set[str]:
    conn = sqlite3.connect(str(db))
    try:
        return {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE ?",
                (like,),
            )
        }
    finally:
        conn.close()


def test_migration_014_creates_image_indexes(temp_sort_db):
    conn = sqlite3.connect(str(temp_sort_db))
    try:
        migrations.apply_migration(conn, MIG_014)
    finally:
        conn.close()
    names = _indexes(temp_sort_db, "idx_images_%")
    assert {
        "idx_images_created_at",
        "idx_images_modified_at",
        "idx_images_filename",
        "idx_images_filesize",
    } <= names


def test_migration_014_creates_video_indexes(temp_sort_db):
    conn = sqlite3.connect(str(temp_sort_db))
    try:
        migrations.apply_migration(conn, MIG_014)
    finally:
        conn.close()
    names = _indexes(temp_sort_db, "idx_videos_%")
    assert {
        "idx_videos_filename",
        "idx_videos_filesize",
        "idx_videos_duration",
        "idx_videos_imported_at",
    } <= names


def test_migration_014_is_idempotent(temp_sort_db):
    for _ in range(2):
        conn = sqlite3.connect(str(temp_sort_db))
        try:
            migrations.apply_migration(conn, MIG_014)  # must not raise on re-run
        finally:
            conn.close()
    assert "idx_images_created_at" in _indexes(temp_sort_db, "idx_images_%")


# --------------------------------------------------------------------------- #
# Task A2 — image sort keys on /api/images (created/modified/filename/size).   #
# --------------------------------------------------------------------------- #


@pytest.fixture
def image_sort_corpus(db, monkeypatch):
    """Three images that disagree on filename, filesize, and created_at."""
    monkeypatch.setattr(deps, "db", db)
    with db.get_session() as s:
        s.add_all(
            [
                Image(
                    id=1,
                    path="library/x/c.webp",
                    filename="c.webp",
                    file_hash="h1",
                    filesize=300,
                    created_at=datetime(2020, 1, 3),
                    modified_at=datetime(2020, 2, 1),
                ),
                Image(
                    id=2,
                    path="library/x/a.webp",
                    filename="a.webp",
                    file_hash="h2",
                    filesize=100,
                    created_at=datetime(2020, 1, 1),
                    modified_at=datetime(2020, 2, 3),
                ),
                Image(
                    id=3,
                    path="library/x/b.webp",
                    filename="b.webp",
                    file_hash="h3",
                    filesize=200,
                    created_at=datetime(2020, 1, 2),
                    modified_at=datetime(2020, 2, 2),
                ),
            ]
        )
        s.commit()
    return db


def _ids(sort: str) -> list[int]:
    r = client.get(f"/api/images?sort={sort}&limit=50")
    assert r.status_code == 200, r.text
    return [img["id"] for img in r.json()["images"]]


def test_image_sort_filename_ascending(image_sort_corpus):
    assert _ids("filename") == [2, 3, 1]  # a, b, c


def test_image_sort_size_descending(image_sort_corpus):
    assert _ids("size") == [1, 3, 2]  # 300, 200, 100


def test_image_sort_created_descending(image_sort_corpus):
    assert _ids("created") == [1, 3, 2]  # 2020-01-03, -02, -01


def test_image_sort_modified_descending(image_sort_corpus):
    assert _ids("modified") == [2, 3, 1]  # 02-03, 02-02, 02-01


def test_image_sort_unknown_falls_back_to_recent(image_sort_corpus):
    # Unknown sort must not 500; it degrades to the default recency order.
    r = client.get("/api/images?sort=bogus&limit=50")
    assert r.status_code == 200, r.text
    assert {img["id"] for img in r.json()["images"]} == {1, 2, 3}


# --------------------------------------------------------------------------- #
# Task A3 — video sort keys on /api/videos (filename/size/duration).          #
# --------------------------------------------------------------------------- #


@pytest.fixture
def video_sort_corpus(db, monkeypatch):
    """Three videos that disagree on filename, filesize, and duration."""
    monkeypatch.setattr(deps, "db", db)
    with db.get_session() as s:
        s.add_all(
            [
                Video(
                    id=1,
                    path="v/c.mp4",
                    filename="c.mp4",
                    file_hash="vh1",
                    filesize=300,
                    duration=30.0,
                    processed=1,
                ),
                Video(
                    id=2,
                    path="v/a.mp4",
                    filename="a.mp4",
                    file_hash="vh2",
                    filesize=100,
                    duration=10.0,
                    processed=1,
                ),
                Video(
                    id=3,
                    path="v/b.mp4",
                    filename="b.mp4",
                    file_hash="vh3",
                    filesize=200,
                    duration=20.0,
                    processed=1,
                ),
            ]
        )
        s.commit()
    return db


def _video_ids(sort: str) -> list[int]:
    r = client.get(f"/api/videos?sort={sort}&limit=50")
    assert r.status_code == 200, r.text
    return [v["id"] for v in r.json()["videos"]]


def test_video_sort_filename_ascending(video_sort_corpus):
    assert _video_ids("filename") == [2, 3, 1]  # a, b, c


def test_video_sort_size_descending(video_sort_corpus):
    assert _video_ids("size") == [1, 3, 2]  # 300, 200, 100


def test_video_sort_duration_descending(video_sort_corpus):
    assert _video_ids("duration") == [1, 3, 2]  # 30, 20, 10


def test_video_sort_unknown_rejected_422(video_sort_corpus):
    # Wave 2b (Task F) tightened the Wave 2a behavior: an unknown video sort now
    # 422s (mirrors /api/search) instead of silently falling back to recent.
    r = client.get("/api/videos?sort=bogus&limit=50")
    assert r.status_code == 422, r.text
    # A valid sort still returns the corpus.
    ok = client.get("/api/videos?sort=recent&limit=50")
    assert ok.status_code == 200
    assert {v["id"] for v in ok.json()["videos"]} == {1, 2, 3}


# --------------------------------------------------------------------------- #
# Task B1 — migration 015 adds videos.poster_locked + its index (idempotent).  #
# --------------------------------------------------------------------------- #

MIG_015 = REPO_ROOT / "data" / "migrations" / "015_poster_locked.sql"


def _video_cols(db: Path) -> set[str]:
    conn = sqlite3.connect(str(db))
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(videos)")}
    finally:
        conn.close()


def test_migration_015_adds_poster_locked(temp_sort_db):
    for _ in range(2):  # idempotent: ADD COLUMN is PRAGMA-guarded by the runner
        conn = sqlite3.connect(str(temp_sort_db))
        try:
            migrations.apply_migration(conn, MIG_015)
        finally:
            conn.close()
    assert "poster_locked" in _video_cols(temp_sort_db)
    assert "idx_videos_poster_locked" in _indexes(temp_sort_db, "idx_videos_%")
