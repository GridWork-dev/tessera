"""
Caption keyword-search lane (webui/search.py::run_search mode="caption").

Standalone FTS5 lane over the ``captions_fts`` table — needs NO query vector and
NO SigLIP text tower, so it must run in well under a second. Read-only.

Two flavours:
  * Synthetic-corpus tests (``test_caption_synthetic_*``) build a tiny temp DB
    with a few images + captions + a populated captions_fts index, so they ALWAYS
    run (real CI coverage of the FTS lane on a clean checkout).
  * Live-DB tests (``test_caption_live_*``) are opt-in box-only checks gated on
    the maintainer's private ``data/catalog.db``; they vanish on a fresh checkout.
"""

import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import webui.search as S
from pipeline.database import Caption, Database, Image, rebuild_caption_fts
from pipeline.migrations import apply_migration

_DB_PATH = Path(__file__).parent.parent / "data" / "catalog.db"
_MIG_008 = Path(__file__).parent.parent / "data" / "migrations" / "008_caption_fts.sql"

# Box-only marker: applied per-test to the live-DB checks ONLY (not the module),
# so the synthetic-corpus tests below always run on a clean public checkout.
_requires_live_db = pytest.mark.skipif(
    not (os.environ.get("RUN_LIVE_DB_TESTS") and _DB_PATH.exists()),
    reason="live-DB tests are opt-in: set RUN_LIVE_DB_TESTS=1 on a box with a populated catalog.db",
)


# --------------------------------------------------------------------------- #
# Synthetic corpus — always runs. Tiny temp DB + populated captions_fts.       #
# --------------------------------------------------------------------------- #
@pytest.fixture
def synthetic_db(tmp_path):
    """A temp catalog with 3 images + captions and a built captions_fts index."""
    db_path = tmp_path / "synthetic.db"
    db = Database(str(db_path))
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
                Caption(image_id=1, model="test", caption="a woman with long hair"),
                Caption(image_id=2, model="test", caption="a man on a beach"),
                Caption(image_id=3, model="test", caption="a woman by a window"),
            ]
        )
        s.commit()
    # Build the FTS5 table (migration 008) + populate it from captions.
    conn = sqlite3.connect(str(db_path))
    apply_migration(conn, _MIG_008)
    indexed = rebuild_caption_fts(conn)
    conn.close()
    assert indexed == 3
    return db


def _search(db, **kw):
    base = dict(
        q=None,
        raw_tags=None,
        mode="caption",
        rating=None,
        person=None,
        sort="relevance",
        page=1,
        page_size=10,
    )
    base.update(kw)
    return S.run_search(db, **base)


def test_caption_synthetic_keyword_matches(synthetic_db):
    out = _search(synthetic_db, q="woman")
    assert out["mode"] == "caption"
    # Both "woman" captions (ids 1 + 3) match; the "man on a beach" does not.
    assert {r["id"] for r in out["results"]} == {1, 3}
    first = out["results"][0]
    assert "id" in first and "tags" in first


def test_caption_synthetic_distinct_term_narrows(synthetic_db):
    out = _search(synthetic_db, q="beach")
    assert out["mode"] == "caption"
    assert {r["id"] for r in out["results"]} == {2}


def test_caption_synthetic_empty_query_degrades_to_tags(synthetic_db):
    out = _search(synthetic_db, q="")
    assert out["mode"] == "tags"
    ws = _search(synthetic_db, q="   ")
    assert ws["mode"] == "tags"


def test_caption_synthetic_punctuation_does_not_raise(synthetic_db):
    # FTS5 operators in user input are quoted into a phrase, so this can't blow up.
    out = _search(synthetic_db, q='a "woman" - hair! (long)')
    assert out["mode"] == "caption"
    assert out["total"] >= 0


# --------------------------------------------------------------------------- #
# Live-DB box-only checks — opt-in, skipped on a clean checkout.               #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def live_db():
    return Database(str(_DB_PATH))


@_requires_live_db
def test_caption_live_mode_returns_results(live_db):
    out = _search(live_db, q="woman")
    assert out["mode"] == "caption"
    assert out["total"] > 0
    assert len(out["results"]) > 0
    first = out["results"][0]
    assert "id" in first and "tags" in first


@_requires_live_db
def test_caption_live_rating_filter_narrows(live_db):
    unfiltered = _search(live_db, q="woman")["total"]
    narrowed = _search(live_db, q="woman", rating="nsfw")["total"]
    assert 0 < narrowed < unfiltered


@_requires_live_db
def test_caption_live_empty_query_degrades_to_tags(live_db):
    out = _search(live_db, q="")
    assert out["mode"] == "tags"
    assert out["total"] > 0
    ws = _search(live_db, q="   ")
    assert ws["mode"] == "tags"


@_requires_live_db
def test_caption_live_punctuation_does_not_raise(live_db):
    out = _search(live_db, q='a "woman" - hair! (long)')
    assert out["mode"] == "caption"
    assert out["total"] >= 0
