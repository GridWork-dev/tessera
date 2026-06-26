"""Wave 2b Task A — generic ``label=<set>:<value>`` filter + per-set facets.

Mirrors tests/test_label_filter setup conventions + the routes_labels temp-DB
fixtures: never touches data/catalog.db. The temp DB is built by the SQLAlchemy
``db`` fixture (images/tags/videos) and then augmented with the label tables via
migrations 002 (user_labels) + 013 (label_sets/definitions/set_id) so the listing
endpoints can JOIN user_labels by set name + value.

Semantics under test (spec 3.5 / plan Task A):
  * AND across different label sets, OR within a single set.
  * legacy ``rating=`` still filters (maps to label=Rating:<v>).
  * ``label_facets`` per-set counts are disjunctive (exclude that set's own selection).
"""

import pytest
from sqlalchemy import text

from pipeline.database import Image, Tag
from pipeline.labels.store import LabelStore
from tests.conftest import add_label_tables

# Import main at module load so its init() binds deps BEFORE any fixture
# monkeypatches deps.db (otherwise a later first import re-binds to the real DB).
from webui.main import app  # noqa: E402


@pytest.fixture
def labeled(db, monkeypatch):
    """Seed images + a Rating (single) and Mood (multi) label set.

    img1: Rating=sfw,  Mood={calm}
    img2: Rating=nsfw, Mood={calm, tense}
    img3: Rating=sfw,  Mood={tense}
    """
    from webui import deps

    monkeypatch.setattr(deps, "db", db)
    with db.get_session() as s:
        s.add_all(
            [
                Image(
                    id=i,
                    path=f"p{i}",
                    filename=f"{i}.webp",
                    file_hash=f"h{i}",
                    width=10,
                    height=10,
                )
                for i in (1, 2, 3)
            ]
        )
        s.add_all(
            [
                Tag(image_id=1, category="clothing", value="dress", tag_source="t"),
                Tag(image_id=2, category="clothing", value="dress", tag_source="t"),
                Tag(image_id=3, category="clothing", value="suit", tag_source="t"),
            ]
        )
        s.commit()
    add_label_tables(db)
    store = LabelStore(db.db_path)
    mood = store.create_set("Mood", single_select=False)
    store.add_value(mood, "calm")
    store.add_value(mood, "tense")
    store.assign_label(1, 1, "sfw")
    store.assign_label(2, 1, "nsfw")
    store.assign_label(3, 1, "sfw")
    store.assign_label(1, mood, "calm")
    store.assign_label(2, mood, "calm")
    store.assign_label(2, mood, "tense")
    store.assign_label(3, mood, "tense")
    return db, mood


def test_filter_single_select_set(labeled):
    from webui.search import run_search

    db, _ = labeled
    out = run_search(
        db,
        q=None,
        raw_tags=[],
        mode="tags",
        rating=None,
        person=None,
        sort="recent",
        page=1,
        page_size=50,
        labels=["Rating:sfw"],
    )
    assert {r["id"] for r in out["results"]} == {1, 3}


def test_filter_or_within_set(labeled):
    from webui.search import run_search

    db, _ = labeled
    out = run_search(
        db,
        q=None,
        raw_tags=[],
        mode="tags",
        rating=None,
        person=None,
        sort="recent",
        page=1,
        page_size=50,
        labels=["Mood:calm", "Mood:tense"],
    )
    # OR within Mood -> all three images have at least one of calm/tense.
    assert {r["id"] for r in out["results"]} == {1, 2, 3}


def test_filter_and_across_sets(labeled):
    from webui.search import run_search

    db, _ = labeled
    out = run_search(
        db,
        q=None,
        raw_tags=[],
        mode="tags",
        rating=None,
        person=None,
        sort="recent",
        page=1,
        page_size=50,
        labels=["Rating:sfw", "Mood:tense"],
    )
    # sfw AND tense -> only img3.
    assert {r["id"] for r in out["results"]} == {3}


def test_legacy_rating_param_maps_to_label(labeled):
    from webui.search import run_search

    db, _ = labeled
    out = run_search(
        db,
        q=None,
        raw_tags=[],
        mode="tags",
        rating="nsfw",
        person=None,
        sort="recent",
        page=1,
        page_size=50,
    )
    assert {r["id"] for r in out["results"]} == {2}


def test_label_facets_disjunctive(labeled):
    from webui.search import compute_label_facets

    db, _ = labeled
    # Active filter: Rating:sfw. Disjunctive facet for the Rating set must IGNORE
    # its own selection (so sibling values still show), but Mood counts respect it.
    facets = compute_label_facets(db, labels=["Rating:sfw"])
    rating = facets["Rating"]
    assert rating["sfw"] == 2
    assert rating["nsfw"] == 1  # not constrained by its own active selection
    mood = facets["Mood"]
    # Mood respects the Rating:sfw constraint -> imgs {1,3}: calm(1), tense(1).
    assert mood["calm"] == 1
    assert mood["tense"] == 1


def test_rating_facet_counts_from_label_set_only(db, monkeypatch):
    """Rating facet counts come purely from the Rating label set (Wave 2c).

    The images.rating column was dropped — facet counts are sourced ONLY from
    user_labels Rating assignments, never a column.
    """
    from webui import deps
    from webui.search import compute_label_facets

    monkeypatch.setattr(deps, "db", db)
    add_label_tables(db)
    store = LabelStore(db.db_path)
    with db.get_session() as s:
        s.add_all(
            [
                Image(
                    id=i,
                    path=f"p{i}",
                    filename=f"{i}.webp",
                    file_hash=f"h{i}",
                    width=10,
                    height=10,
                )
                for i in (1, 2, 3)
            ]
        )
        s.commit()
    store.assign_label(1, 1, "sfw")
    store.assign_label(2, 1, "nsfw")
    store.assign_label(3, 1, "sfw")

    facets = compute_label_facets(db, labels=[])
    rating = facets["Rating"]
    assert rating["sfw"] == 2
    assert rating["nsfw"] == 1


def test_label_facets_owner_scoped(db, monkeypatch):
    """compute_label_facets must respect viewer_owner_id (review finding 1).

    A scoped viewer's per-set counts must not include other owners' rows.
    """
    from webui import deps
    from webui.search import compute_label_facets

    monkeypatch.setattr(deps, "db", db)
    with db.get_session() as s:
        s.add_all(
            [
                Image(
                    id=i,
                    path=f"p{i}",
                    filename=f"{i}.webp",
                    file_hash=f"h{i}",
                    width=10,
                    height=10,
                    owner_id=owner,
                )
                for i, owner in ((1, 1), (2, 2))
            ]
        )
        s.commit()
    add_label_tables(db)
    store = LabelStore(db.db_path)
    mood = store.create_set("Mood", single_select=False)
    store.add_value(mood, "calm")
    store.assign_label(1, mood, "calm")  # owner 1's image
    # Reassign img2 to owner 2 and label it calm too via a direct write
    # (assign_label hardcodes owner_id=1, so write the row manually).
    with db.get_session() as s:
        s.execute(
            text(
                "INSERT INTO user_labels (image_id, set_id, category, value, owner_id) "
                "VALUES (2, :sid, 'Mood', 'calm', 2)"
            ).bindparams(sid=mood)
        )
        s.commit()

    # Viewer owner 1 sees only their own (img1): calm == 1, not 2.
    scoped = compute_label_facets(db, labels=[], viewer_owner_id=1)
    assert scoped["Mood"]["calm"] == 1
    # Unscoped (admin / auth-off) sees both.
    unscoped = compute_label_facets(db, labels=[])
    assert unscoped["Mood"]["calm"] == 2


def test_images_route_label_filter(labeled):
    from fastapi.testclient import TestClient

    db, _ = labeled
    client = TestClient(app)
    r = client.get("/api/images", params={"label": "Rating:nsfw"})
    assert r.status_code == 200
    body = r.json()
    assert {img["id"] for img in body["images"]} == {2}
    assert "label_facets" in body
    assert body["label_facets"]["Rating"]["nsfw"] >= 1
