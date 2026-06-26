"""
Scaffold coverage for webui/search.py:
* caption FTS5 lane (_caption_fts + _fts_match_query) over migration-008 captions_fts
* vec_owner owner_type seam (image scope behavior-identical; scene scope guarded)
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import webui.search as S
from pipeline.database import Caption, Database, Image, rebuild_caption_fts

_FTS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS captions_fts USING fts5("
    "caption, image_id UNINDEXED, tokenize='unicode61 remove_diacritics 2')"
)


def _fts_db(tmp_path):
    db = Database(str(tmp_path / "c.db"))
    with db.get_session() as s:
        img = Image(path="a.webp", file_hash="h1")
        s.add(img)
        s.flush()
        iid = img.id
        s.add(Caption(image_id=iid, model="m", caption="a woman in a red dress"))
        s.commit()
    conn = sqlite3.connect(str(tmp_path / "c.db"))
    conn.execute(_FTS_DDL)
    conn.commit()
    indexed = rebuild_caption_fts(conn)
    conn.close()
    assert indexed == 1
    return db, iid


def test_caption_fts_match_and_candidate_filter(tmp_path):
    db, iid = _fts_db(tmp_path)
    with db.get_session() as s:
        assert S._caption_fts(s, "woman dress", None) == [iid]
        assert S._caption_fts(s, "woman", [iid]) == [iid]
        # candidate set excludes the only hit -> empty
        assert S._caption_fts(s, "woman", []) == []
        # no caption matches -> empty (not an error)
        assert S._caption_fts(s, "helicopter", None) == []


def test_fts_match_query_sanitizes():
    assert S._fts_match_query('a "red" dog!') == '"a" "red" "dog"'
    assert S._fts_match_query("   ") is None
    assert S._fts_match_query(None) is None


def test_vec_owner_seam_scene_scope_guarded(tmp_path):
    db = Database(str(tmp_path / "v.db"))
    with db.get_session() as s:
        s.add(Image(path="a.webp", file_hash="h"))
        s.commit()

    # scene scope is the explicit D4 hook — not wired today.
    with pytest.raises(NotImplementedError):
        S.similar_by_id(db, 1, k=3, raw_tags=None, owner_type="scene")
    with pytest.raises(NotImplementedError):
        S._assert_image_scope("scene")
    S._assert_image_scope("image")  # no raise

    # image scope is behavior-identical: empty store -> graceful degrade.
    res = S.similar_by_id(db, 1, k=3, raw_tags=None)
    assert res.get("vectors_unavailable") is True
