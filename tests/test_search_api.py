"""
Tests for the read-only search API (docs/specs/backend-search-api.md):
GET /api/search, GET /api/search/facets, GET /api/images/{id}/similar.

Two test surfaces, mirroring the existing suite:
* TestClient against the live ``webui.main.app`` (smoke + contract shape), and
* isolated logic tests on a fresh temp DB via the ``db`` fixture (tag AND/OR
  semantics, facet counts, pagination, the vectors-unavailable degradation path).
"""

import warnings

import pytest
from fastapi.testclient import TestClient

from pipeline.database import Image, Tag
from webui import search as search_svc
from webui.main import app

warnings.filterwarnings("ignore")

client = TestClient(app)


# --------------------------------------------------------------------------- #
# Fixtures: a small, deterministic corpus on a temp DB (no vectors).          #
# --------------------------------------------------------------------------- #


@pytest.fixture
def corpus(db):
    """Seed a tiny image+tag corpus with NO vectors (degradation path).

    Layout (rating is the Rating LABEL set now — Wave 2c, no column):
      img1: person=Ana,  clothing=dress, setting=beach, Rating=sfw
      img2: person=Ana,  clothing=dress, setting=studio, Rating=suggestive
      img3: person=Bob,  clothing=suit,  setting=beach, Rating=sfw
    """
    from tests.conftest import add_label_tables, assign_rating

    with db.get_session() as s:
        rows = [
            Image(
                id=1,
                path="library/ana/_unsorted/a.webp",
                filename="a.webp",
                person="Ana",
                file_hash="h1",
                width=10,
                height=10,
            ),
            Image(
                id=2,
                path="library/ana/_unsorted/b.webp",
                filename="b.webp",
                person="Ana",
                file_hash="h2",
                width=10,
                height=10,
            ),
            Image(
                id=3,
                path="library/bob/_unsorted/c.webp",
                filename="c.webp",
                person="Bob",
                file_hash="h3",
                width=10,
                height=10,
            ),
        ]
        s.add_all(rows)
        s.flush()
        tags = [
            Tag(image_id=1, category="clothing", value="dress", tag_source="t"),
            Tag(image_id=1, category="setting", value="beach", tag_source="t"),
            Tag(image_id=2, category="clothing", value="dress", tag_source="t"),
            Tag(image_id=2, category="setting", value="studio", tag_source="t"),
            Tag(image_id=3, category="clothing", value="suit", tag_source="t"),
            Tag(image_id=3, category="setting", value="beach", tag_source="t"),
        ]
        s.add_all(tags)
        s.commit()
    add_label_tables(db)
    assign_rating(db, 1, "sfw")
    assign_rating(db, 2, "suggestive")
    assign_rating(db, 3, "sfw")
    return db


# --------------------------------------------------------------------------- #
# Tag filtering: AND across categories, OR within a category.                 #
# --------------------------------------------------------------------------- #


class TestTagFiltering:
    def test_single_tag_filter(self, corpus):
        out = search_svc.run_search(
            corpus,
            q=None,
            raw_tags=["clothing:dress"],
            mode="tags",
            rating=None,
            person=None,
            sort="recent",
            page=1,
            page_size=50,
        )
        assert out["total"] == 2
        assert {r["id"] for r in out["results"]} == {1, 2}

    def test_or_within_category(self, corpus):
        # clothing in (dress, suit) -> all three images.
        out = search_svc.run_search(
            corpus,
            q=None,
            raw_tags=["clothing:dress", "clothing:suit"],
            mode="tags",
            rating=None,
            person=None,
            sort="recent",
            page=1,
            page_size=50,
        )
        assert out["total"] == 3

    def test_and_across_categories(self, corpus):
        # clothing=dress AND setting=beach -> only img1.
        out = search_svc.run_search(
            corpus,
            q=None,
            raw_tags=["clothing:dress", "setting:beach"],
            mode="tags",
            rating=None,
            person=None,
            sort="recent",
            page=1,
            page_size=50,
        )
        assert out["total"] == 1
        assert out["results"][0]["id"] == 1

    def test_person_filter(self, corpus):
        out = search_svc.run_search(
            corpus,
            q=None,
            raw_tags=[],
            mode="tags",
            rating=None,
            person="Ana",
            sort="recent",
            page=1,
            page_size=50,
        )
        assert out["total"] == 2
        assert {r["id"] for r in out["results"]} == {1, 2}

    def test_rating_label_filter(self, corpus):
        # rating param matches the Rating label set (sfw/suggestive/...).
        out = search_svc.run_search(
            corpus,
            q=None,
            raw_tags=[],
            mode="tags",
            rating="sfw",
            person=None,
            sort="recent",
            page=1,
            page_size=50,
        )
        assert out["total"] == 2
        assert {r["id"] for r in out["results"]} == {1, 3}

    def test_combined_tag_and_rating_and_person(self, corpus):
        out = search_svc.run_search(
            corpus,
            q=None,
            raw_tags=["clothing:dress"],
            mode="tags",
            rating="sfw",
            person="Ana",
            sort="recent",
            page=1,
            page_size=50,
        )
        assert out["total"] == 1
        assert out["results"][0]["id"] == 1


# --------------------------------------------------------------------------- #
# Pagination.                                                                  #
# --------------------------------------------------------------------------- #


class TestPagination:
    def test_pages_are_disjoint_and_sized(self, corpus):
        p1 = search_svc.run_search(
            corpus,
            q=None,
            raw_tags=[],
            mode="tags",
            rating=None,
            person=None,
            sort="recent",
            page=1,
            page_size=2,
        )
        p2 = search_svc.run_search(
            corpus,
            q=None,
            raw_tags=[],
            mode="tags",
            rating=None,
            person=None,
            sort="recent",
            page=2,
            page_size=2,
        )
        assert p1["total"] == 3
        assert len(p1["results"]) == 2
        assert len(p2["results"]) == 1
        ids1 = {r["id"] for r in p1["results"]}
        ids2 = {r["id"] for r in p2["results"]}
        assert ids1.isdisjoint(ids2)


# --------------------------------------------------------------------------- #
# processed filter (tagged vs untagged) — mirrors /api/images semantics.       #
# --------------------------------------------------------------------------- #


@pytest.fixture
def processed_corpus(db):
    """Corpus where img1+img2 are processed=1 (tagged) and img3 is processed=0."""
    with db.get_session() as s:
        s.add_all(
            [
                Image(
                    id=1,
                    path="library/ana/sfw/a.webp",
                    filename="a.webp",
                    person="Ana",
                    file_hash="p1",
                    processed=True,
                    width=10,
                    height=10,
                ),
                Image(
                    id=2,
                    path="library/ana/sfw/b.webp",
                    filename="b.webp",
                    person="Ana",
                    file_hash="p2",
                    processed=True,
                    width=10,
                    height=10,
                ),
                Image(
                    id=3,
                    path="library/bob/sfw/c.webp",
                    filename="c.webp",
                    person="Bob",
                    file_hash="p3",
                    processed=False,
                    width=10,
                    height=10,
                ),
            ]
        )
        s.commit()
    return db


class TestProcessedFilter:
    def _run(self, db, processed):
        return search_svc.run_search(
            db,
            q=None,
            raw_tags=[],
            mode="tags",
            rating=None,
            person=None,
            processed=processed,
            sort="recent",
            page=1,
            page_size=50,
        )

    def test_processed_true_returns_only_tagged(self, processed_corpus):
        out = self._run(processed_corpus, True)
        assert out["total"] == 2
        assert {r["id"] for r in out["results"]} == {1, 2}

    def test_processed_false_returns_only_untagged(self, processed_corpus):
        out = self._run(processed_corpus, False)
        assert out["total"] == 1
        assert {r["id"] for r in out["results"]} == {3}

    def test_processed_none_returns_all(self, processed_corpus):
        out = self._run(processed_corpus, None)
        assert out["total"] == 3

    def test_processed_filter_live_route_200(self):
        # Both values must be accepted by the route and return contract shape.
        for val in ("true", "false"):
            r = client.get(f"/api/search?mode=tags&processed={val}&page_size=2")
            assert r.status_code == 200
            data = r.json()
            assert "results" in data and "total" in data

    def test_processed_does_not_break_degradation(self, processed_corpus):
        # A degrading mode (semantic, no vectors) still honors processed + flags.
        out = search_svc.run_search(
            processed_corpus,
            q="anything",
            raw_tags=[],
            mode="semantic",
            rating=None,
            person=None,
            processed=True,
            sort="relevance",
            page=1,
            page_size=50,
        )
        assert out["vectors_unavailable"] is True
        assert out["mode"] == "tags"
        assert out["total"] == 2  # only the two processed images


# --------------------------------------------------------------------------- #
# Facet counts (disjunctive).                                                  #
# --------------------------------------------------------------------------- #


class TestFacets:
    def test_facet_shape_and_counts_no_filter(self, corpus):
        f = search_svc.compute_facets(corpus, raw_tags=[], rating=None, person=None)
        assert set(f.keys()) == {"categories", "ratings", "people"}
        clothing = {c["value"]: c["count"] for c in f["categories"]["clothing"]}
        assert clothing == {"dress": 2, "suit": 1}
        assert f["ratings"] == {"sfw": 2, "suggestive": 1}
        assert f["people"] == {"Ana": 2, "Bob": 1}

    def test_disjunctive_within_active_category(self, corpus):
        # With clothing=dress active, the clothing facet must STILL show siblings
        # (dress + suit) at their full counts (disjunctive), so the user can OR-in.
        f = search_svc.compute_facets(
            corpus, raw_tags=["clothing:dress"], rating=None, person=None
        )
        clothing = {c["value"]: c["count"] for c in f["categories"]["clothing"]}
        assert clothing == {"dress": 2, "suit": 1}

    def test_other_category_facet_respects_active_filter(self, corpus):
        # With clothing=dress active, the setting facet is constrained to images
        # that are dresses (img1 beach, img2 studio).
        f = search_svc.compute_facets(
            corpus, raw_tags=["clothing:dress"], rating=None, person=None
        )
        setting = {c["value"]: c["count"] for c in f["categories"]["setting"]}
        assert setting == {"beach": 1, "studio": 1}

    def test_facets_endpoint_live(self):
        r = client.get("/api/search/facets")
        assert r.status_code == 200
        data = r.json()
        # Wave 2b adds a generic per-label-set facet block alongside the legacy
        # category/rating/people facets.
        assert set(data.keys()) == {
            "categories",
            "ratings",
            "people",
            "label_facets",
        }
        assert isinstance(data["categories"], dict)
        assert isinstance(data["ratings"], dict)
        assert isinstance(data["label_facets"], dict)


# --------------------------------------------------------------------------- #
# Graceful degradation: no vectors populated.                                  #
# --------------------------------------------------------------------------- #


class TestVectorDegradation:
    def test_semantic_without_vectors_flags_unavailable(self, corpus):
        out = search_svc.run_search(
            corpus,
            q="anything",
            raw_tags=[],
            mode="semantic",
            rating=None,
            person=None,
            sort="relevance",
            page=1,
            page_size=50,
        )
        assert out["vectors_unavailable"] is True
        assert out["degraded_from"] == "semantic"
        assert out["mode"] == "tags"  # degraded effective mode
        # Still returns useful tag-relevance results, never crashes.
        assert out["total"] == 3

    def test_text2image_gated_degrades(self, corpus):
        out = search_svc.run_search(
            corpus,
            q="red dress",
            raw_tags=[],
            mode="text2image",
            rating=None,
            person=None,
            sort="relevance",
            page=1,
            page_size=50,
        )
        assert out["vectors_unavailable"] is True
        assert out["degraded_from"] == "text2image"
        assert out["mode"] == "tags"

    def test_hybrid_without_vectors_falls_back_silently(self, corpus):
        out = search_svc.run_search(
            corpus,
            q="x",
            raw_tags=["clothing:dress"],
            mode="hybrid",
            rating=None,
            person=None,
            sort="relevance",
            page=1,
            page_size=50,
        )
        # Hybrid falls back to tag relevance: results present, mode -> tags,
        # degraded_from recorded, but NOT flagged vectors_unavailable (no hard
        # failure — the request still succeeds usefully).
        assert out["mode"] == "tags"
        assert out["degraded_from"] == "hybrid"
        assert "vectors_unavailable" not in out
        assert out["total"] == 2

    def test_similar_without_vectors_returns_unavailable(self, corpus):
        out = search_svc.similar_by_id(corpus, 1, k=10, raw_tags=[])
        assert out["vectors_unavailable"] is True
        assert out["results"] == []
        assert out["mode"] == "similar"

    def test_similar_unknown_id(self, corpus):
        out = search_svc.similar_by_id(corpus, 99999, k=10, raw_tags=[])
        assert out.get("__not_found__") is True

    def test_vector_count_zero_on_fresh_db(self, corpus):
        assert search_svc.vector_count(corpus) == 0


# --------------------------------------------------------------------------- #
# Request validation (route layer).                                           #
# --------------------------------------------------------------------------- #


class TestRequestValidation:
    def test_invalid_mode_422(self):
        assert client.get("/api/search?mode=bogus").status_code == 422

    def test_invalid_sort_422(self):
        assert client.get("/api/search?sort=bogus").status_code == 422

    def test_malformed_tag_422(self):
        assert client.get("/api/search?tags=noColonHere").status_code == 422

    def test_page_size_bounds_422(self):
        assert client.get("/api/search?page_size=99999").status_code == 422
        assert client.get("/api/search?page=0").status_code == 422

    def test_similar_unknown_id_404_live(self):
        # An id far beyond the live corpus must 404 (image not found), never 500.
        assert client.get("/api/images/99999999/similar").status_code == 404


# --------------------------------------------------------------------------- #
# Live smoke (default hybrid mode against the real catalog).                   #
# --------------------------------------------------------------------------- #


class TestSearchEndpointLive:
    def test_default_search_returns_contract_shape(self):
        r = client.get("/api/search?page_size=3")
        assert r.status_code == 200
        data = r.json()
        for key in ("results", "total", "page", "page_size", "mode"):
            assert key in data
        assert isinstance(data["results"], list)
        assert len(data["results"]) <= 3

    def test_tags_mode_result_item_shape(self):
        r = client.get("/api/search?mode=tags&page_size=1")
        assert r.status_code == 200
        results = r.json()["results"]
        if results:
            item = results[0]
            for key in ("id", "file_hash", "rating", "person", "tags"):
                assert key in item
            assert isinstance(item["tags"], list)
