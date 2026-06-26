"""
Tests for the inspector/dashboard/triage endpoints added for the new UI:

* GET    /api/images/{id}            — full-detail single-image inspector object
* GET    /api/stats/directories      — per-person / per-directory aggregates
* GET    /api/pipeline/throughput    — best-effort recent processing rate
* POST   /api/images/batch/flag      — bulk triage (reuses single-flag logic)
* GET/POST/DELETE /api/images/{id}/labels — manual user_labels CRUD

Two surfaces, mirroring tests/test_webui.py + tests/test_search_api.py:
* TestClient against the live ``webui.main.app`` (smoke + 404 contract), and
* data-dependent tests that point ``webui.deps.db`` at a seeded temp DB via the
  ``db`` fixture, so the route handlers' ``db.get_session()`` hit known rows.
"""

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.database import Caption, Image, Notes, Tag
from webui import deps
from webui.main import app

client = TestClient(app)


# --------------------------------------------------------------------------- #
# Helper: point webui.deps.db at a seeded temp DB for route-level data tests.  #
# --------------------------------------------------------------------------- #


@pytest.fixture
def use_temp_db(db, monkeypatch):
    """Swap the shared ``webui.deps.db`` singleton to a seeded temp DB.

    The route handlers read ``webui.deps.db`` at request time; monkeypatching it
    lets us exercise the real FastAPI routes against a deterministic corpus, then
    restore the live catalog handle automatically at teardown.
    """
    monkeypatch.setattr(deps, "db", db)
    return db


@pytest.fixture
def detail_corpus(use_temp_db):
    """One fully-populated image (tags, note, caption, nudenet) + one bare image.

    Rating is the Rating LABEL set now (Wave 2c): img1=sfw via a Rating label,
    img2 left unrated (no label).
    """
    from tests.conftest import add_label_tables, assign_rating

    db = use_temp_db
    with db.get_session() as s:
        s.add_all(
            [
                Image(
                    id=1,
                    path="library/ana/_unsorted/a.webp",
                    filename="a.webp",
                    directory="library/ana/_unsorted",
                    person="Ana",
                    file_hash="h1",
                    width=100,
                    height=200,
                    filesize=12345,
                    format="webp",
                    processed=True,
                    flagged=False,
                    original_path="/old/IMG_001.jpg",
                    original_filename="IMG_001.jpg",
                    nudenet_regions=json.dumps(
                        [{"label": "FACE_F", "score": 0.9, "box": [1, 2, 3, 4]}]
                    ),
                ),
                Image(
                    id=2,
                    path="library/bob/_unsorted/b.webp",
                    filename="b.webp",
                    directory="library/bob/_unsorted",
                    person="Bob",
                    file_hash="h2",
                    processed=False,
                ),
            ]
        )
        s.flush()
        s.add_all(
            [
                Tag(
                    image_id=1,
                    category="clothing",
                    value="dress",
                    confidence=0.8,
                    tag_source="wd_eva02",
                ),
                Notes(image_id=1, content="creative idea"),
                Caption(image_id=1, model="joycaption", caption="A person in a dress."),
            ]
        )
        s.commit()
    add_label_tables(db)
    assign_rating(db, 1, "sfw")
    return db


# --------------------------------------------------------------------------- #
# 1. GET /api/images/{id} — full-detail inspector.                            #
# --------------------------------------------------------------------------- #


class TestImageDetail:
    def test_full_detail_shape(self, detail_corpus):
        data = client.get("/api/images/1").json()
        # All requested columns present.
        for key in (
            "id",
            "path",
            "filename",
            "directory",
            "person",
            "file_hash",
            "width",
            "height",
            "filesize",
            "format",
            "created_at",
            "modified_at",
            "imported_at",
            "media_type",
            "rating",
            "processed",
            "flagged",
            "flag_action",
            "original_path",
            "original_filename",
            "tags",
            "notes",
            "captions",
            "nudenet_regions",
            "has_embedding",
            "similar_available",
        ):
            assert key in data, f"missing {key}"
        assert data["id"] == 1
        assert data["person"] == "Ana"
        assert data["rating"] == "sfw"
        assert data["processed"] is True
        assert data["width"] == 100 and data["height"] == 200
        assert data["original_filename"] == "IMG_001.jpg"

    def test_nested_collections(self, detail_corpus):
        data = client.get("/api/images/1").json()
        assert data["tags"] == [
            {
                "category": "clothing",
                "value": "dress",
                "confidence": 0.8,
                "tag_source": "wd_eva02",
            }
        ]
        assert data["notes"] == "creative idea"
        assert data["captions"] == [
            {"model": "joycaption", "caption": "A person in a dress."}
        ]
        assert data["nudenet_regions"] == [
            {"label": "FACE_F", "score": 0.9, "box": [1, 2, 3, 4]}
        ]

    def test_empty_pillars_degrade_to_empty_or_null(self, detail_corpus):
        data = client.get("/api/images/2").json()
        assert data["tags"] == []
        assert data["captions"] == []
        assert data["notes"] is None
        assert data["nudenet_regions"] is None
        # No Tier-1 vectors on a fresh temp DB.
        assert data["has_embedding"] is False
        assert data["similar_available"] is False

    def test_no_absolute_path_leak(self, detail_corpus):
        data = client.get("/api/images/1").json()
        assert data["path"] == "library/ana/_unsorted/a.webp"
        assert not data["path"].startswith("/")

    def test_unknown_id_404(self):
        assert client.get("/api/images/99999999").status_code == 404


# --------------------------------------------------------------------------- #
# 2. GET /api/stats/directories — aggregates.                                  #
# --------------------------------------------------------------------------- #


class TestDirectoryStats:
    def test_person_and_directory_aggregates(self, detail_corpus):
        data = client.get("/api/stats/directories").json()
        assert "by_person" in data and "by_directory" in data
        by_person = {r["key"]: r for r in data["by_person"]}
        assert set(by_person) == {"Ana", "Bob"}
        ana = by_person["Ana"]
        assert ana["image_count"] == 1
        assert ana["processed_count"] == 1
        assert ana["flagged_count"] == 0
        assert ana["ratings"] == {"sfw": 1}
        bob = by_person["Bob"]
        assert bob["processed_count"] == 0
        assert bob["ratings"] == {"unrated": 1}

    def test_directory_grouping(self, detail_corpus):
        data = client.get("/api/stats/directories").json()
        dirs = {r["key"] for r in data["by_directory"]}
        assert dirs == {"library/ana/_unsorted", "library/bob/_unsorted"}

    def test_live_route_200(self):
        r = client.get("/api/stats/directories")
        assert r.status_code == 200
        assert "by_person" in r.json()


# --------------------------------------------------------------------------- #
# 3. GET /api/pipeline/throughput — best-effort rate.                          #
# --------------------------------------------------------------------------- #


class TestThroughput:
    def test_shape_and_graceful_zero(self, use_temp_db):
        # Fresh empty temp DB: nothing imported -> graceful zero, never fabricated.
        data = client.get("/api/pipeline/throughput").json()
        for key in ("window_minutes", "count", "per_minute", "signal", "latest_at"):
            assert key in data
        assert data["count"] == 0
        assert data["per_minute"] == 0.0
        assert data["latest_at"] is None
        assert data["signal"] == "imported_at"

    def test_recent_imports_counted(self, use_temp_db):
        db = use_temp_db
        with db.get_session() as s:
            # imported_at defaults to datetime.now() -> within the window.
            s.add_all(
                [
                    Image(id=1, path="p/1.webp", file_hash="t1"),
                    Image(id=2, path="p/2.webp", file_hash="t2"),
                ]
            )
            s.commit()
        data = client.get("/api/pipeline/throughput?minutes=10").json()
        assert data["count"] == 2
        assert data["per_minute"] == round(2 / 10, 2)
        assert data["latest_at"] is not None

    def test_window_bounds_422(self):
        assert client.get("/api/pipeline/throughput?minutes=0").status_code == 422
        assert client.get("/api/pipeline/throughput?minutes=99999").status_code == 422

    def test_live_route_200(self):
        assert client.get("/api/pipeline/throughput").status_code == 200


# --------------------------------------------------------------------------- #
# 4. POST /api/images/batch/flag — bulk triage.                               #
# --------------------------------------------------------------------------- #


class TestBatchFlag:
    def test_batch_maybe_updates_all(self, detail_corpus):
        r = client.post(
            "/api/images/batch/flag",
            json={"image_ids": [1, 2], "action": "maybe"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["updated"] == 2
        assert all(res["ok"] for res in data["results"])
        # Verify the flag actually persisted via the detail endpoint.
        assert client.get("/api/images/1").json()["flag_action"] == "maybe"
        assert client.get("/api/images/1").json()["flagged"] is True

    def test_batch_reports_unknown_ids_as_partial(self, detail_corpus):
        r = client.post(
            "/api/images/batch/flag",
            json={"image_ids": [1, 99999], "action": "keep"},
        )
        data = r.json()
        assert data["updated"] == 1
        by_id = {res["id"]: res for res in data["results"]}
        assert by_id[1]["ok"] is True
        assert by_id[99999]["ok"] is False

    def test_batch_invalid_action_400(self, detail_corpus):
        r = client.post(
            "/api/images/batch/flag",
            json={"image_ids": [1], "action": "bogus"},
        )
        assert r.status_code == 400

    def test_batch_bad_ids_type_400(self, detail_corpus):
        r = client.post(
            "/api/images/batch/flag",
            json={"image_ids": "not-a-list", "action": "keep"},
        )
        assert r.status_code == 400


# --------------------------------------------------------------------------- #
# 5. user_labels CRUD.                                                         #
# --------------------------------------------------------------------------- #


class TestUserLabels:
    def test_add_list_delete_roundtrip(self, detail_corpus):
        # Initially empty.
        assert client.get("/api/images/1/labels").json()["labels"] == []

        # Add.
        created = client.post("/api/images/1/labels", data={"value": "favorite"}).json()
        assert created["value"] == "favorite"
        assert created["category"] == "user"
        label_id = created["id"]

        # List shows it.
        labels = client.get("/api/images/1/labels").json()["labels"]
        assert any(label["id"] == label_id for label in labels)

        # Delete.
        d = client.delete(f"/api/images/1/labels/{label_id}")
        assert d.status_code == 200
        assert client.get("/api/images/1/labels").json()["labels"] == []

    def test_add_is_idempotent(self, detail_corpus):
        first = client.post("/api/images/1/labels", data={"value": "dup"}).json()
        second = client.post("/api/images/1/labels", data={"value": "dup"}).json()
        # Same (image, category, value) -> same row, no duplicate.
        assert first["id"] == second["id"]
        labels = client.get("/api/images/1/labels").json()["labels"]
        assert sum(1 for label in labels if label["value"] == "dup") == 1

    def test_add_to_unknown_image_404(self, detail_corpus):
        r = client.post("/api/images/99999/labels", data={"value": "x"})
        assert r.status_code == 404

    def test_custom_category(self, detail_corpus):
        created = client.post(
            "/api/images/1/labels",
            data={"value": "outdoor", "category": "scene"},
        ).json()
        assert created["category"] == "scene"
