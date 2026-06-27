"""
Tests for ADR-0005 GATE 0 — scripts/verify_self_retrieval.py.

The pure decision logic (``evaluate_probe`` / ``classify_readiness``) is tested
with synthetic inputs — NO torch, NO real vectors, NO network. An optional live
check invokes the script's ``main`` against the real catalog.db and asserts it
exits 0 (ready) — the H100 full embed run has landed (26,590 vectors in
``vec_siglip_1152``), so GATE 0 now passes.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.verify_self_retrieval import (  # noqa: E402
    DEFAULT_DB,
    classify_readiness,
    evaluate_probe,
)


# --------------------------------------------------------------------------- #
# evaluate_probe — top-1 must be self AND cosine must clear the threshold.     #
# --------------------------------------------------------------------------- #
def test_evaluate_probe_self_and_high_cosine_passes():
    assert evaluate_probe(56, neighbor_id=56, cosine=0.999, threshold=0.99)


def test_evaluate_probe_wrong_neighbor_fails():
    # Top neighbor is some other image — poisoned / degenerate space.
    assert not evaluate_probe(56, neighbor_id=999, cosine=0.999, threshold=0.99)


def test_evaluate_probe_cosine_below_threshold_fails():
    # Right neighbor but cosine at/under the bar (wrong-checkpoint collapse).
    assert not evaluate_probe(56, neighbor_id=56, cosine=0.95, threshold=0.99)


def test_evaluate_probe_cosine_exactly_threshold_fails():
    # Strictly greater-than: equal to the threshold does NOT pass.
    assert not evaluate_probe(56, neighbor_id=56, cosine=0.99, threshold=0.99)


def test_evaluate_probe_no_neighbor_fails():
    assert not evaluate_probe(56, neighbor_id=None, cosine=0.0, threshold=0.99)


# --------------------------------------------------------------------------- #
# classify_readiness — coverage + all-probes-present gate.                     #
# --------------------------------------------------------------------------- #
def test_classify_readiness_few_vectors_is_insufficient():
    # Today's shape: 65 vectors over a 26,590-image corpus.
    assert (
        classify_readiness(
            vectors_present=65,
            corpus_size=26590,
            probe_ids_present=4,
            probe_ids_total=10,
        )
        == "insufficient"
    )


def test_classify_readiness_full_coverage_all_probes_is_ready():
    assert (
        classify_readiness(
            vectors_present=26590,
            corpus_size=26590,
            probe_ids_present=10,
            probe_ids_total=10,
        )
        == "ready"
    )


def test_classify_readiness_full_coverage_but_missing_probe_is_insufficient():
    # Plenty of vectors overall, but a probe id has no stored vector to hit.
    assert (
        classify_readiness(
            vectors_present=26590,
            corpus_size=26590,
            probe_ids_present=9,
            probe_ids_total=10,
        )
        == "insufficient"
    )


def test_classify_readiness_unknown_corpus_is_insufficient():
    assert (
        classify_readiness(
            vectors_present=100,
            corpus_size=0,
            probe_ids_present=10,
            probe_ids_total=10,
        )
        == "insufficient"
    )


# --------------------------------------------------------------------------- #
# Synthetic-corpus main() check — ALWAYS runs. A tiny temp DB with a corpus     #
# but only a sliver of vectors must report "insufficient" and exit 2, with NO   #
# torch import (the heavy run_gate branch is only reached when readiness=ready).#
# --------------------------------------------------------------------------- #
def test_main_synthetic_insufficient_exits_2(tmp_path, capsys):
    import json

    import numpy as np

    from pipeline.database import Database, Image
    from pipeline.tier1_embedder import ensure_vec_table, open_vec_db, upsert_vec
    from scripts.verify_self_retrieval import main

    db_path = tmp_path / "synthetic.db"
    db = Database(str(db_path))
    # A 20-image corpus...
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
                for i in range(1, 21)
            ]
        )
        s.commit()
    # ...with vectors for only the 2 probe ids -> coverage 2/20 == 10% << 90%.
    conn = open_vec_db(str(db_path))
    try:
        ensure_vec_table(conn)
        for pid in (1, 2):
            upsert_vec(conn, pid, np.ones(1152, dtype=np.float32))
        conn.commit()
    finally:
        conn.close()

    code = main(["--db", str(db_path), "--ids", "[1, 2]"])
    assert code == 2  # insufficient — full embed run has not "landed"
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["status"] == "insufficient"
    assert report["corpus_size"] == 20
    assert report["probe_ids_present"] == 2


# --------------------------------------------------------------------------- #
# Optional live check (box-only): H100 embed run landed -> probes pass, exit 0.#
# Opt-in; skipped on a clean checkout where data/catalog.db is absent.         #
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    not (os.environ.get("RUN_LIVE_DB_TESTS") and Path(DEFAULT_DB).exists()),
    reason="live-DB test is opt-in: set RUN_LIVE_DB_TESTS=1 on a box with the real catalog.db",
)
def test_main_exits_0_on_real_db_with_embeddings(capsys):
    from scripts.verify_self_retrieval import main

    code = main(["--db", str(DEFAULT_DB)])
    assert code == 0  # ready — full embed run landed, all probes self-retrieve
    out = capsys.readouterr().out
    assert '"status": "ready"' in out
