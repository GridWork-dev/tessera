"""
Tests for pipeline/preference.py — Track 5 scaffold (degrade-first).

Builds a tiny in-memory corpus via ``Database(':memory:')`` with a handful of
Image rows whose ``flag_action`` is mostly NULL — mirroring the real DB (0
keep/reject labels, no usable vectors). Asserts every entry point DEGRADES with
a sensible reason and never fabricates a score. No torch, no real vectors.

``Database(':memory:')`` -> ``open_vec_db(':memory:')`` opens a SEPARATE empty
in-memory DB with no vec table, so ``vector_count`` / vec lookups return 0 — the
exact vectors-unavailable condition we want to exercise.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np  # noqa: E402

from pipeline import preference as pref  # noqa: E402
from pipeline.database import Database, Image  # noqa: E402
from pipeline.preference import (  # noqa: E402
    MIN_PER_CLASS,
    REASON_INSUFFICIENT_LABELS,
    REASON_VECTORS_UNAVAILABLE,
    _centroid,
    _fit_probe,
    _l2_normalize_rows,
    _probe_margin,
    centroid_preview,
    preference_ranked_ids,
    preference_status,
    train_probe,
)


def _trainable_status() -> dict:
    """A preference_status snapshot that reports the probe as trainable."""
    return {
        "keep": 110,
        "reject": 110,
        "maybe": 0,
        "vectors": 220,
        "min_per_class": MIN_PER_CLASS,
        "trainable": True,
        "reason": None,
    }


def _separable_labels(d: int = 16, n: int = 110, seed: int = 0):
    """Synthetic L2-normed keep/reject vectors that a linear probe separates."""
    rng = np.random.default_rng(seed)
    pos = rng.normal(1.0, 0.1, size=(n, d))
    neg = rng.normal(-1.0, 0.1, size=(n, d))
    X = np.vstack([pos, neg])
    y = np.concatenate([np.ones(n), np.zeros(n)])
    return X, y


@pytest.fixture
def mem_db():
    """In-memory DB with a few images; most flag_action NULL (like the real DB)."""
    db = Database(":memory:")
    with db.get_session() as s:
        s.add_all(
            [
                Image(id=1, path="library/a/sfw/1.webp", file_hash="h1"),
                Image(id=2, path="library/a/sfw/2.webp", file_hash="h2"),
                # A single 'keep' — far below MIN_PER_CLASS, still untrainable.
                Image(
                    id=3,
                    path="library/a/sfw/3.webp",
                    file_hash="h3",
                    flag_action="keep",
                ),
                Image(
                    id=4,
                    path="library/a/sfw/4.webp",
                    file_hash="h4",
                    flag_action="maybe",
                ),
            ]
        )
        s.commit()
    return db


def test_status_not_trainable_insufficient_labels(mem_db):
    status = preference_status(mem_db)
    assert status["trainable"] is False
    # Labels are the binding constraint (well under MIN_PER_CLASS), so that's the
    # reported reason even with 0 vectors.
    assert status["reason"] == REASON_INSUFFICIENT_LABELS
    assert status["keep"] == 1
    assert status["reject"] == 0
    assert status["maybe"] == 1
    assert status["vectors"] == 0
    assert status["min_per_class"] == MIN_PER_CLASS


def test_train_probe_degrades(mem_db):
    out = train_probe(mem_db)
    assert out["ok"] is False
    assert out["reason"] == REASON_INSUFFICIENT_LABELS
    # The full status snapshot is merged in for the caller/UI.
    assert out["trainable"] is False
    assert out["keep"] == 1


def test_centroid_preview_vectors_unavailable(mem_db):
    out = centroid_preview(mem_db, positive_ids=[1, 2])
    assert out["ok"] is False
    assert out["vectors_unavailable"] is True
    assert out["reason"] == REASON_VECTORS_UNAVAILABLE
    assert out["positives_requested"] == 2
    assert out["positives_found"] == 0


def test_centroid_preview_no_positive_ids(mem_db):
    out = centroid_preview(mem_db, positive_ids=[])
    assert out["ok"] is False
    # An empty request is a usage error, not a vectors problem.
    assert out["vectors_unavailable"] is False


def test_preference_ranked_ids_degrades_to_empty(mem_db):
    out = preference_ranked_ids(mem_db)
    assert out["ok"] is False
    assert out["reason"] == REASON_INSUFFICIENT_LABELS
    assert out["results"] == []


# --- numerical core (pure; no DB) -------------------------------------------


def test_fit_probe_separates_synthetic():
    X, y = _separable_labels(d=8, n=60, seed=0)
    Xn = _l2_normalize_rows(X)
    w, b, thr = _fit_probe(Xn, y)
    margins = _probe_margin(Xn, w, b)
    acc = ((margins >= thr).astype(int) == y.astype(int)).mean()
    assert acc >= 0.95
    assert margins[:60].mean() > margins[60:].mean()


def test_centroid_scores_positives_above_far():
    rng = np.random.default_rng(1)
    pos = _l2_normalize_rows(rng.normal(1.0, 0.05, size=(20, 8)))
    far = _l2_normalize_rows(rng.normal(-1.0, 0.05, size=(20, 8)))
    c = _centroid(pos)
    assert (pos @ c).mean() > (far @ c).mean()
    assert abs(float(np.linalg.norm(c)) - 1.0) < 1e-6


def test_centroid_with_negatives_is_unit():
    rng = np.random.default_rng(7)
    pos = _l2_normalize_rows(rng.normal(1.0, 0.05, size=(10, 8)))
    neg = _l2_normalize_rows(rng.normal(-1.0, 0.05, size=(10, 8)))
    c = _centroid(pos, neg)
    assert abs(float(np.linalg.norm(c)) - 1.0) < 1e-6


# --- trainable paths (monkeypatched DB loaders) -----------------------------


def _corpus_three():
    """Deterministic corpus: keep-like / boundary (orthogonal to the separating
    direction) / reject-like, so margin order and the most-uncertain item are
    stable without depending on the fitted weights."""
    d = 16
    keep_like = np.ones(d)
    boundary = np.tile([1.0, -1.0], d // 2)  # orthogonal to ones -> margin ~ threshold
    reject_like = -np.ones(d)
    mat = _l2_normalize_rows(np.vstack([keep_like, boundary, reject_like]))
    return [10, 20, 30], mat.astype(np.float32)


def test_train_probe_runs_when_trainable(monkeypatch):
    X, y = _separable_labels(d=16, n=110, seed=2)
    monkeypatch.setattr(pref, "preference_status", lambda db: _trainable_status())
    monkeypatch.setattr(pref, "_load_labeled_vectors", lambda db: (X, y, 110, 110))
    out = train_probe(object())
    assert out["ok"] is True
    assert out["n_pos"] == 110 and out["n_neg"] == 110
    assert out["dim"] == 16
    assert out["accuracy"] >= 0.9


def test_preference_ranked_returns_sorted_ids(monkeypatch):
    X, y = _separable_labels(d=16, n=110, seed=3)
    monkeypatch.setattr(pref, "preference_status", lambda db: _trainable_status())
    monkeypatch.setattr(pref, "_load_labeled_vectors", lambda db: (X, y, 110, 110))
    monkeypatch.setattr(pref, "_all_corpus_vectors", lambda db: _corpus_three())
    out = preference_ranked_ids(object(), limit=2)
    assert out["ok"] is True
    assert out["results"] == [10, 20]  # most keep-like first, capped at limit


def test_edge_cases_returns_most_uncertain_first(monkeypatch):
    X, y = _separable_labels(d=16, n=110, seed=4)
    monkeypatch.setattr(pref, "preference_status", lambda db: _trainable_status())
    monkeypatch.setattr(pref, "_load_labeled_vectors", lambda db: (X, y, 110, 110))
    monkeypatch.setattr(pref, "_all_corpus_vectors", lambda db: _corpus_three())
    out = pref.edge_case_ids(object(), limit=1)
    assert out["ok"] is True
    assert out["results"] == [20]  # margin nearest threshold = most uncertain


def test_centroid_preview_runs_with_vectors(monkeypatch):
    rng = np.random.default_rng(5)
    pos_mat = _l2_normalize_rows(rng.normal(1.0, 0.05, size=(3, 16))).astype(np.float32)
    monkeypatch.setattr(
        pref, "_vectors_for_ids", lambda db, ids: (pos_mat[: len(ids)], list(ids))
    )
    monkeypatch.setattr(pref, "_has_corpus_coverage", lambda db: True)
    corpus_ids = list(range(50))
    corpus = _l2_normalize_rows(rng.normal(0.0, 1.0, size=(50, 16))).astype(np.float32)
    monkeypatch.setattr(pref, "_all_corpus_vectors", lambda db: (corpus_ids, corpus))
    out = centroid_preview(object(), positive_ids=[1, 2, 3], threshold=0.0)
    assert out["ok"] is True
    assert isinstance(out["above_threshold"], int)
    assert out["scored"] == 50
    assert out["positives_found"] == 3
