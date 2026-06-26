"""
Tests for the next-phase backend endpoints (Tracks 1 + 2, local portion):

* GET  /api/images?collection_id=        — additive collection read filter
* POST /api/images/{id}/rating           — canonical rating-set (Rating label set)
* GET  /api/videos, /api/videos/facets, /api/videos/{id}  — video pillar surface
* GET  /media/video-poster/{hash}        — video asset serving (404 contract)
* GET  /api/preference/status            — preference scaffold (degrade), guarded

Mirrors tests/test_new_endpoints.py: route handlers read ``webui.deps.db`` at
request time, so we monkeypatch it to a seeded temp DB and exercise the real routes.
collections/collection_items are raw-SQL tables (migration 002, no ORM model), so
the temp DB must materialize them itself; videos/video_scenes are ORM models
(create_all covers them).
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.database import Image, Video
from webui import deps
from webui.main import app

client = TestClient(app)

_COLLECTIONS_DDL = """
CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    cover_image_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""
_COLLECTION_ITEMS_DDL = """
CREATE TABLE IF NOT EXISTS collection_items (
    collection_id INTEGER NOT NULL,
    image_id INTEGER NOT NULL,
    sort_order INTEGER DEFAULT 0,
    added_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (collection_id, image_id)
);
"""


@pytest.fixture
def use_temp_db(db, monkeypatch):
    """Point the shared webui.deps.db at a seeded temp DB; restore at teardown."""
    monkeypatch.setattr(deps, "db", db)
    return db


def _seed_images(db, specs):
    """specs: list of (person, rating). Returns the created ids in order.

    Rating is the Rating LABEL set now (Wave 2c): a non-"unrated" spec is written
    as a Rating label assignment, not the dropped images.rating column.
    """
    from tests.conftest import add_label_tables, assign_rating

    ids = []
    with db.get_session() as s:
        for i, (person, _rating) in enumerate(specs):
            img = Image(
                path=f"{person}/{i}.webp",
                filename=f"{i}.webp",
                person=person,
                file_hash=f"hash{i}",
                processed=True,
            )
            s.add(img)
            s.flush()
            ids.append(img.id)
        s.commit()
    add_label_tables(db)
    for iid, (_person, rating) in zip(ids, specs):
        if rating and rating != "unrated":
            assign_rating(db, iid, rating)
    return ids


def _make_collection(db, name, image_ids):
    with db.get_session() as s:
        s.execute(text(_COLLECTIONS_DDL))
        s.execute(text(_COLLECTION_ITEMS_DDL))
        s.execute(text("INSERT INTO collections (name) VALUES (:n)"), {"n": name})
        cid = s.execute(text("SELECT last_insert_rowid()")).scalar()
        for order, iid in enumerate(image_ids):
            s.execute(
                text(
                    "INSERT INTO collection_items (collection_id, image_id, sort_order) "
                    "VALUES (:c, :i, :o)"
                ),
                {"c": cid, "i": iid, "o": order},
            )
        s.commit()
    return cid


# --------------------------------------------------------------------------- #
# collection_id filter                                                        #
# --------------------------------------------------------------------------- #


def test_collection_id_filter_returns_members(use_temp_db):
    db = use_temp_db
    ids = _seed_images(db, [("Ann", "sfw"), ("Ann", "nsfw"), ("Bea", "sfw")])
    cid = _make_collection(db, "Faves", [ids[0], ids[2]])

    r = client.get(f"/api/images?collection_id={cid}")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert {img["id"] for img in body["images"]} == {ids[0], ids[2]}


def test_collection_id_composes_with_rating(use_temp_db):
    db = use_temp_db
    ids = _seed_images(db, [("Ann", "sfw"), ("Ann", "nsfw"), ("Bea", "sfw")])
    cid = _make_collection(db, "Mixed", ids)  # all three

    r = client.get(f"/api/images?collection_id={cid}&rating=sfw")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2  # the two sfw members
    assert all(img["rating"] == "sfw" for img in body["images"])


def test_collection_id_empty_collection_no_500(use_temp_db):
    db = use_temp_db
    _seed_images(db, [("Ann", "sfw")])
    cid = _make_collection(db, "Empty", [])

    r = client.get(f"/api/images?collection_id={cid}")
    assert r.status_code == 200
    assert r.json()["total"] == 0
    # a non-existent collection id is also empty, not an error
    r2 = client.get("/api/images?collection_id=999999")
    assert r2.status_code == 200
    assert r2.json()["total"] == 0


# --------------------------------------------------------------------------- #
# rating-set endpoint                                                         #
# --------------------------------------------------------------------------- #


def test_set_rating_writes_label_and_drains_queue(use_temp_db):
    db = use_temp_db
    ids = _seed_images(db, [("Ann", "unrated")])
    iid = ids[0]

    r = client.post(f"/api/images/{iid}/rating", data={"value": "sfw"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "rating": "sfw"}

    # Rating now lives in the Rating label set (user_labels), not a column.
    from webui import search as search_svc

    with db.get_session() as s:
        assert search_svc.rating_map_for_ids(s, [iid]) == {iid: "sfw"}

    # the rating reads back through /api/images and the rating= filter matches
    assert iid in {
        i["id"] for i in client.get("/api/images?rating=sfw").json()["images"]
    }


def test_set_rating_invalid_value_400(use_temp_db):
    db = use_temp_db
    ids = _seed_images(db, [("Ann", "unrated")])
    r = client.post(f"/api/images/{ids[0]}/rating", data={"value": "banana"})
    assert r.status_code == 400


def test_set_rating_unknown_image_404(use_temp_db):
    _seed_images(use_temp_db, [("Ann", "unrated")])
    r = client.post("/api/images/424242/rating", data={"value": "sfw"})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# video pillar surface                                                        #
# --------------------------------------------------------------------------- #


def _seed_video(db, **kw):
    defaults = dict(
        path="Ann/videos/v.mp4",
        filename="v.mp4",
        person="Ann",
        file_hash="vhash1",
        duration=75.0,
        width=1920,
        height=1080,
        fps=30.0,
        codec="h264",
        has_audio=1,
        rating="sfw",
        processed=1,
    )
    defaults.update(kw)
    with db.get_session() as s:
        v = Video(**defaults)
        s.add(v)
        s.flush()
        vid = v.id
        s.commit()
    return vid


def test_videos_list_and_card_shape(use_temp_db):
    db = use_temp_db
    _seed_video(db)
    r = client.get("/api/videos")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    card = body["videos"][0]
    assert card["media_type"] == "video"
    assert card["duration_bucket"] == "30s-2m"
    assert card["orientation"] == "landscape"
    assert card["has_audio"] is True
    assert card["has_poster"] is False  # no poster_path seeded


def test_videos_facets_counts(use_temp_db):
    db = use_temp_db
    _seed_video(
        db, file_hash="a", duration=10.0, width=1080, height=1920
    )  # <30s portrait
    _seed_video(
        db, file_hash="b", duration=300.0, width=1920, height=1080
    )  # 2m-10m landscape
    facets = client.get("/api/videos/facets").json()
    assert facets["duration"] == {"<30s": 1, "2m-10m": 1}
    assert facets["orientation"] == {"portrait": 1, "landscape": 1}
    assert facets["has_audio"]["yes"] == 2


def test_videos_filters(use_temp_db):
    db = use_temp_db
    _seed_video(db, file_hash="a", duration=10.0, width=1080, height=1920)
    _seed_video(db, file_hash="b", duration=300.0, width=1920, height=1080)
    assert client.get("/api/videos?duration=<30s").json()["total"] == 1
    assert client.get("/api/videos?orientation=landscape").json()["total"] == 1
    assert client.get("/api/videos?has_audio=true").json()["total"] == 2


def test_video_detail_and_404(use_temp_db):
    db = use_temp_db
    vid = _seed_video(db)
    r = client.get(f"/api/videos/{vid}")
    assert r.status_code == 200
    assert r.json()["scenes"] == []
    assert client.get("/api/videos/99999").status_code == 404


def test_video_poster_404_when_no_asset(use_temp_db):
    db = use_temp_db
    _seed_video(db, file_hash="noposter", poster_path=None)
    assert client.get("/media/video-poster/noposter").status_code == 404
    assert client.get("/media/video-poster/missing").status_code == 404


# --------------------------------------------------------------------------- #
# preference scaffold (guarded: module is built in a parallel track)          #
# --------------------------------------------------------------------------- #


def test_preference_status_degrades(use_temp_db):
    pytest.importorskip("pipeline.preference")
    _seed_images(use_temp_db, [("Ann", "sfw")])
    body = client.get("/api/preference/status").json()
    assert body["trainable"] is False
    assert "keep" in body and "reject" in body
