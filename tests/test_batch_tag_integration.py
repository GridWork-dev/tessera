"""
Regression test for the review's CRITICAL finding: the legacy VLM end-save block
must NOT flip processed=1 for an image whose Tier-0 failed (zero tags), defeating
the per-image finalize gate and stranding the image forever (processed=0 is the
resume key). Drives the real batch_tag.main() control flow with stubbed taggers.
"""

import sqlite3
import sys

import yaml

import batch_tag
from pipeline.database import Database, Image


class _FakeTier0:
    """Tier-0 that raises for any image whose relative path contains 'A'."""

    def __init__(self, *a, **k):
        pass

    def tag_image(self, rel_path, session, image_id, db):
        if "A" in str(rel_path):
            raise RuntimeError("tier0 boom")
        rows = [
            {
                "category": "tags",
                "value": "woman",
                "confidence": 0.9,
                "tag_source": "wd_eva02",
            },
            {
                "category": "rating",
                "value": "general",
                "confidence": 0.8,
                "tag_source": "wd_eva02",
            },
        ]
        db.add_tags_scored(session, image_id, rows)
        return rows


def test_tier0_failure_leaves_image_unprocessed(tmp_path, monkeypatch):
    # Temp catalog with two images; A will fail Tier-0, B will succeed.
    db_path = tmp_path / "catalog.db"
    db = Database(str(db_path))
    with db.get_session() as s:
        s.add(Image(path="A.webp", filename="A.webp", file_hash="hA", processed=False))
        s.add(Image(path="B.webp", filename="B.webp", file_hash="hB", processed=False))
        s.commit()

    # Minimal config the script reads.
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {"project_root": str(tmp_path), "database": {"path": "catalog.db"}}
        )
    )

    # Real (existing) files so the loop's path.exists() check passes.
    file_a = tmp_path / "A_real.webp"
    file_b = tmp_path / "B_real.webp"
    file_a.write_bytes(b"x")
    file_b.write_bytes(b"x")
    resolved = {"A.webp": file_a, "B.webp": file_b}
    monkeypatch.setattr(batch_tag, "resolve_image_path", lambda p: resolved[p])

    # Stub the heavy taggers (no ONNX / NudeNet load).
    monkeypatch.setattr("pipeline.tier0_tagger.Tier0Tagger", _FakeTier0)
    monkeypatch.setattr(
        "pipeline.tier3_nudenet.Tier3NudeNet.detect_image", lambda self, p: []
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["batch_tag.py", "--config", str(cfg), "--tiers", "0,3", "--count", "10"],
    )
    batch_tag.main()

    conn = sqlite3.connect(str(db_path))
    rows = dict(conn.execute("SELECT path, processed FROM images").fetchall())
    tag_counts = dict(
        conn.execute(
            "SELECT i.path, COUNT(t.id) FROM images i "
            "LEFT JOIN tags t ON t.image_id = i.id AND t.tag_source='wd_eva02' "
            "GROUP BY i.path"
        ).fetchall()
    )
    conn.close()

    # B succeeded: processed + has tags.
    assert rows["B.webp"] == 1
    assert tag_counts["B.webp"] >= 1
    # A failed Tier-0: must remain unprocessed with zero Tier-0 tags (re-selectable).
    assert rows["A.webp"] == 0, "Tier-0-failed image was wrongly marked processed=1"
    assert tag_counts["A.webp"] == 0
