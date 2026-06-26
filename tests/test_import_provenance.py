"""
Track 1e: import_h100_artifacts.py persists the run_manifest.json it previously
discarded — one model_runs row per tier + run_id stamped on imported tags/captions.
Runs the real importer against a synthetic temp catalog + artifacts dir.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.database import Caption, Database, Image, ModelRun, Tag
from scripts import import_h100_artifacts as imp


def test_import_persists_run_manifest_and_stamps_run_id(tmp_path):
    db_path = tmp_path / "cat.db"
    db = Database(str(db_path))
    with db.get_session() as s:
        s.add(Image(path="p/1.webp", file_hash="h1"))
        s.add(Image(path="p/2.webp", file_hash="h2"))
        s.commit()

    art = tmp_path / "outputs" / "stamp123" / "artifacts"
    art.mkdir(parents=True)
    (art / "tags.jsonl").write_text(
        json.dumps(
            {
                "id": 1,
                "rows": [
                    {
                        "category": "tags",
                        "value": "woman",
                        "confidence": 0.9,
                        "tag_source": "wd_eva02",
                    }
                ],
            }
        )
        + "\n"
    )
    (art / "captions.jsonl").write_text(
        json.dumps({"id": 2, "caption": "a person"}) + "\n"
    )

    (tmp_path / "manifest.json").write_text(
        json.dumps({"1": {"person": "x"}, "2": {"person": "y"}})
    )
    (art.parent / "run_manifest.json").write_text(
        json.dumps(
            {
                "written": {"tier0": 1, "tier2": 1},
                "siglip_model": "google/siglip-so400m-patch14-384",
                "joycaption_db_model": "llama-joycaption-beta-one",
                "n_images": 2,
            }
        )
    )

    rc = imp.main(
        [
            "--artifacts",
            str(art),
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--run-manifest",
            str(art.parent / "run_manifest.json"),
            "--db",
            str(db_path),
            "--tiers",
            "0,2",
            "--skip-backup",
        ]
    )
    assert rc == 0

    with db.get_session() as s:
        runs = {r.tier: r for r in s.query(ModelRun).all()}
        assert set(runs) == {"tier0", "tier2"}
        assert runs["tier0"].run_key == "stamp123:tier0"
        assert runs["tier0"].item_count == 1
        assert runs["tier2"].model_id == "llama-joycaption-beta-one"
        # full manifest preserved verbatim
        assert json.loads(runs["tier0"].manifest_json)["n_images"] == 2

        tag = s.query(Tag).filter(Tag.value == "woman").first()
        assert tag.run_id == runs["tier0"].id
        cap = s.query(Caption).first()
        assert cap.run_id == runs["tier2"].id


def test_import_without_run_manifest_is_unchanged(tmp_path):
    """Backwards compatible: no --run-manifest => no model_runs, NULL run_id."""
    db_path = tmp_path / "cat.db"
    db = Database(str(db_path))
    with db.get_session() as s:
        s.add(Image(path="p/1.webp", file_hash="h1"))
        s.commit()
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "tags.jsonl").write_text(
        json.dumps(
            {
                "id": 1,
                "rows": [
                    {
                        "category": "tags",
                        "value": "x",
                        "confidence": 0.5,
                        "tag_source": "joytag",
                    }
                ],
            }
        )
        + "\n"
    )
    (tmp_path / "manifest.json").write_text(json.dumps({"1": {}}))
    rc = imp.main(
        [
            "--artifacts",
            str(art),
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--db",
            str(db_path),
            "--tiers",
            "0",
            "--skip-backup",
        ]
    )
    assert rc == 0
    with db.get_session() as s:
        assert s.query(ModelRun).count() == 0
        assert s.query(Tag).filter(Tag.value == "x").first().run_id is None
