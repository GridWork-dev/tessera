"""
Tests for Wave-1-finish — SigLIP 2 re-embed (dry-run/plan) + nsfw-2-mini.

PURE logic only: the re-embed plan/swap-SQL/gate builders and the nsfw rating
mapping are exercised with synthetic inputs — NO torch, NO model weights, NO GPU,
NO network, and NEVER the real ``data/catalog.db``. The heavy ``classify`` path
is covered with a fake (monkeypatched) model and guarded by ``skipif`` so it
never demands torch on a torch-less box.

Mirrors tests/test_self_retrieval.py: the repo root is inserted on sys.path at
the top so the worktree's code (not any installed copy) is exercised.
"""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import nsfw2mini  # noqa: E402
from scripts import reembed_siglip2 as reembed  # noqa: E402

HAS_TORCH = importlib.util.find_spec("torch") is not None


# --------------------------------------------------------------------------- #
# nsfw2mini — pure rating mapping (all 5 classes + unknown).                   #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("safe", "sfw"),  # the real benign class in the published weights
        ("SAFE", "sfw"),
        ("Normal", "sfw"),  # alias for model-card prose
        ("Drawing", "sfw"),
        ("Sexy", "suggestive"),
        ("Porn", "nsfw"),
        ("Hentai", "nsfw"),
        ("  porn  ", "nsfw"),  # whitespace + case normalized
        ("NORMAL", "sfw"),
        ("garbage", "unrated"),  # unknown -> never guess
        ("", "unrated"),
        (None, "unrated"),
    ],
)
def test_derive_rating_from_label(label, expected):
    assert nsfw2mini.derive_rating_from_label(label) == expected


def test_label_to_rating_covers_all_five_classes():
    # The five classes from the published weights (id2label) are all mapped, no
    # silent gap. The benign class is "safe" (verified), not "normal".
    assert {"safe", "drawing", "sexy", "porn", "hentai"} <= set(
        nsfw2mini.LABEL_TO_RATING
    )


def test_derive_rating_from_probs_argmax():
    probs = {"Normal": 0.1, "Sexy": 0.2, "Porn": 0.7}
    assert nsfw2mini.derive_rating_from_probs(probs) == "nsfw"


def test_derive_rating_from_probs_suggestive_wins():
    probs = {"Normal": 0.3, "Sexy": 0.6, "Porn": 0.1}
    assert nsfw2mini.derive_rating_from_probs(probs) == "suggestive"


def test_derive_rating_from_probs_empty_is_unrated():
    assert nsfw2mini.derive_rating_from_probs({}) == "unrated"


def test_nsfw2mini_imports_without_torch():
    # Module-level import must not require torch (heavy deps are lazy).
    assert nsfw2mini.MODEL_ID == "viddexa/nsfw-detection-2-mini"
    assert hasattr(nsfw2mini, "Nsfw2MiniClassifier")


@pytest.mark.skipif(not HAS_TORCH, reason="torch not installed")
def test_classify_with_fake_model(tmp_path, monkeypatch):
    """classify() drives a fake model end-to-end: image -> {label: prob} softmax.

    No real weights / network: model, processor, and the image-resolve are all
    stubbed so the test exercises the wrapper's own glue (softmax + id2label
    zip), not transformers.
    """
    import numpy as np
    import torch
    from PIL import Image as PILImage

    # A throwaway 8x8 RGB image on disk, resolved via a patched path resolver.
    img_path = tmp_path / "img.webp"
    PILImage.fromarray(np.zeros((8, 8, 3), dtype=np.uint8)).save(img_path)
    monkeypatch.setattr(nsfw2mini, "resolve_image_path", lambda _: img_path)

    class _FakeInputs(dict):
        def to(self, _):
            return self

    class _FakeOut:
        # Logits favoring class 0 ("Normal") -> sfw.
        logits = torch.tensor([[5.0, 0.0, 0.0, 0.0, 0.0]])

    clf = nsfw2mini.Nsfw2MiniClassifier()
    clf.model = lambda **_: _FakeOut()
    clf.processor = lambda **_: _FakeInputs()
    clf.device = torch.device("cpu")
    clf.id2label = {0: "Normal", 1: "Porn", 2: "Hentai", 3: "Drawing", 4: "Sexy"}
    monkeypatch.setattr(clf, "_load", lambda: None)

    result = clf.classify("a/img.webp")
    assert max(result, key=result.get) == "Normal"
    assert clf.rating_for("a/img.webp") == "sfw"


# --------------------------------------------------------------------------- #
# reembed_siglip2 — pure plan / swap-SQL / gate decision.                      #
# --------------------------------------------------------------------------- #
def test_temp_index_path_appends_new():
    p = reembed.temp_index_path("/data/turbovec_siglip.idx")
    assert p.name == "turbovec_siglip.idx.new"


def test_build_swap_sql_drops_then_renames():
    sql = reembed.build_swap_sql()
    assert "DROP TABLE vec_siglip_1152" in sql
    assert "RENAME TO vec_siglip_1152" in sql
    assert "vec_siglip_1152_new" in sql
    # Drop must come before the rename (order matters for the atomic swap).
    assert sql.index("DROP TABLE") < sql.index("RENAME TO")


def test_gate_passed_all_true():
    assert reembed.gate_passed([{"pass": True}, {"pass": True}])


def test_gate_passed_any_false_fails():
    assert not reembed.gate_passed([{"pass": True}, {"pass": False}])


def test_gate_passed_empty_never_passes():
    # A gate that checked zero probes must not authorize discarding the old store.
    assert not reembed.gate_passed([])


def test_build_plan_shape():
    plan = reembed.build_plan(
        db_path="/tmp/x.db",
        index_path="/data/turbovec_siglip.idx",
        corpus_size=26590,
        probe_ids=[1, 2, 3],
        threshold=0.99,
        apply=False,
        ack_text_tower=False,
    )
    assert plan["model_transition"]["to"] == "google/siglip2-so400m-patch14-384"
    assert plan["embedding_dim"] == 1152
    assert plan["schema_change"] is False
    assert plan["temp_vec_table"] == "vec_siglip_1152_new"
    assert plan["temp_index"].endswith(".idx.new")
    assert "text_embedder.py" in plan["text_tower_lockstep"]
    assert len(plan["steps"]) == 6


# --------------------------------------------------------------------------- #
# CLI — dry-run touches nothing; --apply without --ack-text-tower refuses.     #
# --------------------------------------------------------------------------- #
def _temp_db(tmp_path: Path) -> str:
    """Build a fresh TEMP sqlite db with an images table (never the real db)."""
    db_path = tmp_path / "catalog.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE images (id INTEGER PRIMARY KEY, path TEXT)")
    conn.executemany(
        "INSERT INTO images (id, path) VALUES (?, ?)",
        [(1, "a/1.webp"), (2, "a/2.webp")],
    )
    conn.commit()
    conn.close()
    return str(db_path)


def test_main_dry_run_default_mutates_nothing(tmp_path, capsys):
    db_path = _temp_db(tmp_path)
    idx = tmp_path / "turbovec_siglip.idx"
    code = reembed.main(["--db", db_path, "--index", str(idx), "--ids", "[1,2]"])
    assert code == 0
    out = capsys.readouterr().out
    assert '"job": "siglip2-reembed-safe-swap"' in out
    assert "DRY-RUN" in out
    # Nothing on disk created: no temp index, no live index.
    assert not idx.exists()
    assert not reembed.temp_index_path(idx).exists()


def test_main_apply_without_ack_refuses(tmp_path, capsys):
    db_path = _temp_db(tmp_path)
    idx = tmp_path / "turbovec_siglip.idx"
    code = reembed.main(
        ["--db", db_path, "--index", str(idx), "--ids", "[1,2]", "--apply"]
    )
    assert code == 2  # refuses to mutate without the lockstep ack
    err = capsys.readouterr().err
    assert "text_embedder.py" in err
    assert not idx.exists()


def test_corpus_size_counts_rows(tmp_path):
    db_path = _temp_db(tmp_path)
    assert reembed.corpus_size(db_path) == 2


def test_corpus_size_missing_db_is_zero(tmp_path):
    assert reembed.corpus_size(str(tmp_path / "nope.db")) == 0


def test_load_probe_ids_inline_json():
    assert reembed.load_probe_ids("[5, 6, 7]") == [5, 6, 7]
