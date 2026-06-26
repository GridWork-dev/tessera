"""Fast, model-free, write-free tests for the nearest-centroid tagger."""

from __future__ import annotations

import numpy as np
import pytest

from pipeline import centroid_tagger as ct


def _unit_rows(rng: np.random.Generator, n: int, dim: int) -> np.ndarray:
    mat = rng.standard_normal((n, dim)).astype(np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    return (mat / norms).astype(np.float32)


def test_compute_centroid_is_unit_norm_and_normalized_mean():
    rng = np.random.default_rng(0)
    vectors = _unit_rows(rng, 5, 1152)
    centroid = ct.compute_centroid(vectors)

    assert centroid.shape == (1152,)
    assert centroid.dtype == np.float32
    assert np.linalg.norm(centroid) == pytest.approx(1.0, abs=1e-5)

    expected = vectors.mean(axis=0)
    expected = expected / np.linalg.norm(expected)
    np.testing.assert_allclose(centroid, expected, atol=1e-5)


def test_compute_centroid_rejects_empty():
    with pytest.raises(ValueError):
        ct.compute_centroid(np.empty((0, 1152), dtype=np.float32))


def test_score_all_cosines_in_range_and_self_score_one():
    rng = np.random.default_rng(1)
    matrix = _unit_rows(rng, 10, 1152)
    centroid = matrix[0]  # a stored unit vector

    scores = ct.score_all(centroid, matrix)

    assert scores.shape == (10,)
    assert scores.min() >= -1.0 - 1e-5
    assert scores.max() <= 1.0 + 1e-5
    # cosine of a unit vector with itself is 1.0
    assert scores[0] == pytest.approx(1.0, abs=1e-5)


def test_score_all_empty_matrix():
    centroid = np.zeros(1152, dtype=np.float32)
    scores = ct.score_all(centroid, np.empty((0, 1152), dtype=np.float32))
    assert scores.shape == (0,)


class _FakeDB:
    """Serves canned (id, unit-vector) rows; records any tag writes."""

    def __init__(self, ids, matrix):
        self._ids = list(ids)
        self._matrix = matrix
        self.writes: list[tuple[int, list[dict]]] = []
        self.db_path = ":memory:"

    # patched-in surrogates for load helpers (avoid sqlite-vec entirely)
    def add_tags_scored(self, session, image_id, rows, run_id=None):
        self.writes.append((image_id, rows))

    def get_session(self):  # context manager
        class _Ctx:
            def __enter__(self_inner):
                return object()

            def __exit__(self_inner, *exc):
                return False

        return _Ctx()


@pytest.fixture
def fake_corpus(monkeypatch):
    rng = np.random.default_rng(2)
    ids = list(range(100, 110))
    matrix = _unit_rows(rng, 10, 1152)
    db = _FakeDB(ids, matrix)

    def fake_load_all(_db):
        return list(db._ids), db._matrix

    def fake_load_for_ids(_db, want):
        idx = [db._ids.index(i) for i in want if i in db._ids]
        return db._matrix[idx]

    monkeypatch.setattr(ct, "load_all_vectors", fake_load_all)
    monkeypatch.setattr(ct, "load_vectors_for_ids", fake_load_for_ids)
    return db, ids, matrix


def test_preview_counts_above_threshold(fake_corpus):
    db, ids, matrix = fake_corpus
    # exemplar = first row; with a very low threshold every row passes.
    res = ct.preview(db, [ids[0]], threshold=-1.0)
    assert res["count"] == 10
    assert res["total"] == 10
    # the exemplar itself scores 1.0 and should be the top sample entry.
    assert res["sample"][0][0] == ids[0]
    assert res["sample"][0][1] == pytest.approx(1.0, abs=1e-5)

    # a threshold above any cosine yields zero.
    res_high = ct.preview(db, [ids[0]], threshold=1.5)
    assert res_high["count"] == 0
    assert res_high["sample"] == []


def test_apply_dry_run_writes_nothing(fake_corpus):
    db, ids, _ = fake_corpus
    res = ct.apply(db, [ids[0]], category="tags", value="x", threshold=-1.0)
    assert res["dry_run"] is True
    assert res["written"] == 0
    assert db.writes == []


def test_apply_real_write_invokes_add_tags_scored(fake_corpus):
    db, ids, _ = fake_corpus
    res = ct.apply(
        db,
        [ids[0]],
        category="tags",
        value="x",
        threshold=-1.0,
        confidence=0.9,
        dry_run=False,
    )
    assert res["dry_run"] is False
    assert res["written"] == 10
    assert len(db.writes) == 10
    _, rows = db.writes[0]
    assert rows[0]["tag_source"] == "centroid"
    assert rows[0]["category"] == "tags"
    assert rows[0]["value"] == "x"
    assert rows[0]["confidence"] == 0.9
