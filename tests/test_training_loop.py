"""Training learning-loop coverage:
* video person derivation for the _inbound_videos/<Model>/ handoff layout
* exclude/hide suggestion mining from rejects (pipeline/suggestions.py)
* preference recommend/edge feeds degrade-first (no labels/vectors today)
* the three new endpoints return their degrade shapes
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from pipeline import preference, suggestions
from pipeline.database import Database, ExclusionRule, Image, Tag
from pipeline.video_ingest import _derive_person
from webui.main import app

client = TestClient(app)


# ---- video person derivation (P0-2) ----


def test_derive_person_inbound_videos():
    # The model folder IS the person in the handoff layout.
    assert _derive_person("_inbound_videos/Jane_Doe/abc.mp4") == "Jane_Doe"
    # Library layout still works.
    assert _derive_person("library/John_Doe/sfw/x.webp") == "John_Doe"
    # Unknown layouts -> None.
    assert _derive_person("_unsorted/nsfw/x.webp") is None
    assert _derive_person("loose.mp4") is None


# ---- exclude/hide suggestions ----


def _seed_rejects(db: Database) -> None:
    with db.get_session() as s:
        # 4 rejected images all tagged content_type=watermark; 3 also clothing=lingerie.
        for i in range(4):
            img = Image(
                path=f"r{i}.webp", file_hash=f"r{i}", flagged=True, flag_action="reject"
            )
            s.add(img)
            s.flush()
            s.add(Tag(image_id=img.id, category="content_type", value="watermark"))
            if i < 3:
                s.add(Tag(image_id=img.id, category="clothing", value="lingerie"))
            # rating tags must be ignored as candidates
            s.add(Tag(image_id=img.id, category="rating", value="nsfw"))
        # A kept image with the same tag must NOT inflate the reject count.
        kept = Image(path="k.webp", file_hash="k", flagged=True, flag_action="keep")
        s.add(kept)
        s.flush()
        s.add(Tag(image_id=kept.id, category="content_type", value="watermark"))
        s.commit()


def test_exclusion_candidates_empty(tmp_path):
    db = Database(str(tmp_path / "e.db"))
    out = suggestions.exclusion_candidates(db)
    assert out["candidates"] == []
    assert out["reject_count"] == 0


def test_exclusion_candidates_ranks_and_filters(tmp_path):
    db = Database(str(tmp_path / "s.db"))
    _seed_rejects(db)

    out = suggestions.exclusion_candidates(db, min_count=3)
    assert out["reject_count"] == 4
    cands = {(c["category"], c["value"]): c["reject_count"] for c in out["candidates"]}
    # watermark on 4 rejects, lingerie on 3 — both clear min_count=3.
    assert cands[("content_type", "watermark")] == 4
    assert cands[("clothing", "lingerie")] == 3
    # rating tags are never candidates.
    assert ("rating", "nsfw") not in cands
    # ranked by reject_count desc.
    assert out["candidates"][0]["value"] == "watermark"

    # min_count gate: at 4, only watermark qualifies.
    only4 = suggestions.exclusion_candidates(db, min_count=4)
    vals = {c["value"] for c in only4["candidates"]}
    assert vals == {"watermark"}


def test_exclusion_candidates_filters_existing_rules(tmp_path):
    db = Database(str(tmp_path / "x.db"))
    _seed_rejects(db)
    with db.get_session() as s:
        s.add(ExclusionRule(category="content_type", value="watermark"))
        s.commit()

    out = suggestions.exclusion_candidates(db, min_count=3)
    vals = {c["value"] for c in out["candidates"]}
    assert "watermark" not in vals  # already excluded -> dropped
    assert "lingerie" in vals


# ---- preference feeds degrade-first ----


def test_edge_case_ids_degrades(tmp_path):
    db = Database(str(tmp_path / "p.db"))
    res = preference.edge_case_ids(db, limit=10)
    assert res["ok"] is False
    assert res["reason"] == "insufficient_labels"
    assert res["results"] == []


# ---- endpoint shapes (real db: 0 rejects / no vectors -> degrade) ----


def test_suggestions_endpoint_ok():
    r = client.get("/api/suggestions/exclusions")
    assert r.status_code == 200
    body = r.json()
    assert "candidates" in body and "reject_count" in body


def test_recommend_and_edge_endpoints_degrade():
    for path in ("/api/preference/recommend", "/api/preference/edge-cases"):
        r = client.get(path)
        assert r.status_code == 200, path
        body = r.json()
        assert body["items"] == []
        assert body["degraded"] is True
        assert body["reason"] in ("insufficient_labels", "vectors_unavailable")
