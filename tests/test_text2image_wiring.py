"""
SigLIP text-tower wiring contract (ADR-0006) for webui/search.py.

Asserts the query-vector seam and the degradation gate WITHOUT loading any
model: ``_text_query_vector`` short-circuits on empty/None input before importing
the embedder, and the text2image gate is monkeypatched so no real torch forward
ever runs. Fast (no model load, tiny temp DB).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import webui.search as S
from pipeline.database import Database, Image


def test_text_query_vector_empty_is_none():
    # Empty / whitespace / None must return None BEFORE any embedder import, so
    # the vector modes degrade and no model is loaded for a blank query.
    assert S._text_query_vector("") is None
    assert S._text_query_vector(None) is None
    assert S._text_query_vector("   ") is None


def test_text2image_degrades_when_gate_not_passed(tmp_path, monkeypatch):
    # Build a tiny DB so run_search has candidates (no vectors needed — the gate
    # forces degradation before the vector path is reached).
    db = Database(str(tmp_path / "t2i.db"))
    with db.get_session() as s:
        s.add(Image(path="a.webp", file_hash="h1"))
        s.commit()

    # Make can_embed_text TRUE without loading a model: a non-None fake blob.
    # This proves the gate alone (TEXT2IMAGE_GATE_PASSED False, the default) is
    # what forces degradation — not the absence of a query vector.
    monkeypatch.setattr(S, "_text_query_vector", lambda q: b"\x00" * 4)
    monkeypatch.setattr(S, "TEXT2IMAGE_GATE_PASSED", False)

    out = S.run_search(
        db,
        q="x",
        raw_tags=None,
        mode="text2image",
        rating=None,
        person=None,
        sort="relevance",
        page=1,
        page_size=10,
    )
    assert out["mode"] == "tags"
    assert out["degraded_from"] == "text2image"
    assert out.get("vectors_unavailable") is True
