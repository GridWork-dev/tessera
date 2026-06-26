"""
Tests for Tier 1 — SigLIP SO400M embeddings + turbovec / sqlite-vec stores.

The real SigLIP model is NEVER loaded (skipped when transformers is absent, e.g.
the MacBook venv). The real catalog.db is NEVER touched — tests use an in-memory
or temp store only. turbovec store tests are guarded by importorskip so the
suite collects cleanly when turbovec is unavailable.
"""

import numpy as np
import pytest

# importorskip the module itself so a missing torch/transformers (lazy-imported
# only inside methods) never breaks collection — the module top imports only
# numpy / turbovec / PIL / sqlite-vec.
tier1 = pytest.importorskip("pipeline.tier1_embedder")

from pipeline.tier1_embedder import (  # noqa: E402
    VEC_TABLE,
    Tier1Embedder,
    l2_normalize,
    serialize_float32,
)


def test_embedding_dim_is_1152():
    """SO400M hidden_size is 1152 — embedder.py / ADR / the project guidelines are stale."""
    assert Tier1Embedder.EMBEDDING_DIM == 1152


def test_model_id():
    assert Tier1Embedder.MODEL_ID == "google/siglip-so400m-patch14-384"


def test_l2_normalize_unit_length():
    out = l2_normalize(np.array([3.0, 4.0], dtype=np.float32))
    assert out.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(out), 1.0, atol=1e-6)


def test_l2_normalize_zero_vector_safe():
    out = l2_normalize(np.zeros(4, dtype=np.float32))
    np.testing.assert_array_equal(out, np.zeros(4, dtype=np.float32))


def test_serialize_float32_roundtrip():
    vec = np.arange(1152, dtype=np.float32)
    blob = serialize_float32(vec)
    assert len(blob) == 1152 * 4
    np.testing.assert_array_equal(np.frombuffer(blob, dtype=np.float32), vec)


def _synthetic_vectors():
    """Three near-orthogonal unit 1152-d vectors with known ids."""
    rng = np.random.default_rng(0)
    base = rng.standard_normal((3, 1152)).astype(np.float32)
    vecs = np.stack([l2_normalize(v) for v in base])
    ids = [101, 202, 303]
    return ids, vecs


def test_turbovec_store_add_search_nearest_id():
    """Build the index, add 3 synthetic vectors, assert nearest id is correct."""
    pytest.importorskip("turbovec")
    from pipeline.tier1_embedder import TurboVecStore

    store = TurboVecStore(dim=1152, bit_width=4, path="/dev/null/never")
    ids, vecs = _synthetic_vectors()
    store.add_batch(ids, vecs)

    for expect_id, query in zip(ids, vecs):
        results = store.search(query, k=1)
        assert results, "search returned no results"
        nearest_id, score = results[0]
        assert nearest_id == expect_id


def test_turbovec_store_contains_and_idempotent_add():
    pytest.importorskip("turbovec")
    from pipeline.tier1_embedder import TurboVecStore

    store = TurboVecStore(dim=1152, bit_width=4, path="/dev/null/never")
    ids, vecs = _synthetic_vectors()
    store.add_batch(ids, vecs)
    assert store.contains(101)
    assert not store.contains(999)

    # Re-adding the same ids is a no-op (no ValueError from duplicate ids).
    store.add_batch(ids, vecs)
    assert store.search(vecs[0], k=1)[0][0] == 101


def test_turbovec_store_write_load_roundtrip(tmp_path):
    pytest.importorskip("turbovec")
    from pipeline.tier1_embedder import TurboVecStore

    idx_path = tmp_path / "siglip.idx"
    store = TurboVecStore(dim=1152, bit_width=4, path=idx_path)
    ids, vecs = _synthetic_vectors()
    store.add_batch(ids, vecs)
    store.save()
    assert idx_path.exists()

    reopened = TurboVecStore(dim=1152, bit_width=4, path=idx_path)
    assert reopened.contains(202)
    assert reopened.search(vecs[1], k=1)[0][0] == 202


def test_vec_rescore_table_create_and_query(tmp_path):
    """The float rescore table is named vec_siglip_1152 and is float[1152]."""
    sqlite_vec = pytest.importorskip("sqlite_vec")  # noqa: F841
    from pipeline.tier1_embedder import (
        ensure_vec_table,
        open_vec_db,
        upsert_vec,
    )

    db_path = tmp_path / "rescore.db"
    conn = open_vec_db(db_path)
    ensure_vec_table(conn)

    ids, vecs = _synthetic_vectors()
    for image_id, vec in zip(ids, vecs):
        upsert_vec(conn, image_id, vec)
    conn.commit()

    count = conn.execute(f"SELECT COUNT(*) FROM {VEC_TABLE}").fetchone()[0]
    assert count == 3

    # Cosine-distance KNN: querying with a stored vector returns itself first.
    blob = serialize_float32(vecs[0])
    row = conn.execute(
        f"""
        SELECT image_id FROM {VEC_TABLE}
        WHERE embedding MATCH ? AND k = 1
        ORDER BY distance
        """,
        (blob,),
    ).fetchone()
    assert row[0] == ids[0]

    # upsert is idempotent — re-inserting the same id keeps the row count at 3.
    upsert_vec(conn, ids[0], vecs[0])
    conn.commit()
    assert conn.execute(f"SELECT COUNT(*) FROM {VEC_TABLE}").fetchone()[0] == 3
    conn.close()
