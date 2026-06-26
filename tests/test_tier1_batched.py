"""
Batched SigLIP embed path — spec docs/specs/batched-siglip-embed.md.

``embed_images_batched`` must be numerically identical (within 1e-4) to looping
``embed_image``, preserve order, handle a ragged final batch, and ``embed_unprocessed``
must keep the per-N checkpoint cadence + crash resumability of the per-image path.

PARITY runs against the REAL SigLIP SO400M when it loads from the local HF cache
(offline); otherwise it is skipped and the manual integration check below covers it.
ORDER / RAGGED / CHECKPOINT / CRASH tests stub the batched primitive so no GPU/model
load happens — mirroring test_tier1_checkpoint.py.
"""

import os
import tempfile

import numpy as np
import pytest

tier1 = pytest.importorskip("pipeline.tier1_embedder")
pytest.importorskip("turbovec")
pytest.importorskip("sqlite_vec")

from pipeline.database import Image  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers / fixtures
# --------------------------------------------------------------------------- #
def _make_images(n: int) -> list[str]:
    """Write ``n`` deterministic, distinct RGB PNGs to a temp dir.

    Returns ABSOLUTE paths — resolve_image_path() passes absolute paths through
    unchanged, so the live content root is never touched.
    """
    from PIL import Image as PILImage

    tmp = tempfile.mkdtemp(prefix="tier1_batched_")
    rng = np.random.default_rng(1234)
    paths: list[str] = []
    for i in range(n):
        arr = rng.integers(0, 256, (384, 384, 3), dtype=np.uint8)
        p = os.path.join(tmp, f"img{i}.png")
        PILImage.fromarray(arr).save(p)
        paths.append(p)
    return paths


def _load_real_embedder():
    """Load the real SigLIP embedder offline, or return None to skip.

    Forces HF offline so the test never reaches the network; if the model is not
    cached (or torch/transformers absent) the parity test is skipped, not failed.
    """
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    try:
        emb = tier1.Tier1Embedder()
        emb._load()
        return emb
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# (a) PARITY — batched vs per-image, real model on small N
# --------------------------------------------------------------------------- #
def test_batched_matches_per_image_real_model():
    """Real SigLIP: batched rows match embed_image within 1e-4 per element."""
    emb = _load_real_embedder()
    if emb is None:
        pytest.skip("SigLIP SO400M not available offline; see manual parity check")

    paths = _make_images(6)  # small N — one forward, fast
    singles = np.stack([emb.embed_image(p) for p in paths])
    batched = emb.embed_images_batched(paths)

    assert batched.shape == (len(paths), tier1.Tier1Embedder.EMBEDDING_DIM)
    # Each row L2-normalized.
    np.testing.assert_allclose(np.linalg.norm(batched, axis=1), 1.0, atol=1e-5)
    # The gate: per-element max-abs-delta below 1e-4 for every image.
    for i in range(len(paths)):
        delta = float(np.max(np.abs(singles[i] - batched[i])))
        assert delta < 1e-4, f"row {i} parity delta {delta} >= 1e-4"


# --------------------------------------------------------------------------- #
# (b) ORDER preservation — distinct stub vectors per path
# --------------------------------------------------------------------------- #
def test_batched_preserves_order(monkeypatch):
    """Row i of the batch output maps to rel_paths[i] after stack/unstack."""

    # Stub get_image_features so the i-th image yields a vector keyed to its
    # filename index — no real model. _load() still imports torch lazily; stub it
    # to a no-op so no GPU/model load happens.
    monkeypatch.setattr(tier1.Tier1Embedder, "_load", lambda self: None)

    rel_paths = [f"/abs/path/img{i}.png" for i in range(5)]

    class _Pooled:
        def __init__(self, mat):
            self.pooler_output = mat

    import torch

    def fake_open(path):  # PILImage.open replacement
        class _Img:
            def convert(self, mode):
                # carry the path index so the "model" can read order back out
                idx = int(str(path).split("img")[1].split(".")[0])
                return idx

        return _Img()

    monkeypatch.setattr(tier1.PILImage, "open", fake_open)

    captured = {}

    def fake_processor(images, return_tensors):
        captured["order"] = list(images)  # list of idx ints, in input order

        class _Inputs(dict):
            def to(self, device):
                return self

        return _Inputs()

    def fake_get_image_features(**inputs):
        # Build a [K,1152] tensor where row j has its idx in column 0.
        order = captured["order"]
        mat = torch.zeros(len(order), tier1.Tier1Embedder.EMBEDDING_DIM)
        for j, idx in enumerate(order):
            mat[j, 0] = float(idx) + 1.0  # +1 so L2-norm is nonzero
        return _Pooled(mat)

    emb = tier1.Tier1Embedder()
    emb.processor = fake_processor
    emb.device = "cpu"

    class _Model:
        def get_image_features(self, **inputs):
            return fake_get_image_features(**inputs)

    emb.model = _Model()

    out = emb.embed_images_batched(rel_paths)
    assert out.shape == (5, tier1.Tier1Embedder.EMBEDDING_DIM)
    # After per-row L2-normalize, only column 0 is nonzero -> it becomes 1.0 for
    # every row, but the ORDER of inputs handed to the processor must equal the
    # input order (0,1,2,3,4). That is the order guarantee.
    assert captured["order"] == [0, 1, 2, 3, 4]
    # And each row is the unit vector e0 (nonzero only at col 0) -> norm 1.
    np.testing.assert_allclose(np.linalg.norm(out, axis=1), 1.0, atol=1e-6)
    assert np.allclose(out[:, 0], 1.0)


# --------------------------------------------------------------------------- #
# (b') ORDER end-to-end via embed_unprocessed — id<->vector mapping
# --------------------------------------------------------------------------- #
def test_embed_unprocessed_maps_ids_to_correct_vectors(db, monkeypatch, tmp_path):
    """Each image_id ends up indexed with the vector for ITS path, not a neighbor's."""
    with db.get_session() as s:
        for i in range(5):
            s.add(Image(path=f"path{i}", filename=f"path{i}", file_hash=f"hh{i}"))
        s.commit()

    # Distinct one-hot vector per path -> verifiable id<->vector mapping.
    def fake_embed_batch(self, rel_paths):
        rows = []
        for rp in rel_paths:
            idx = int(rp.replace("path", ""))
            v = np.zeros(1152, dtype=np.float32)
            v[idx] = 1.0
            rows.append(v)
        return np.asarray(rows, dtype=np.float32)

    monkeypatch.setattr(tier1.Tier1Embedder, "embed_images_batched", fake_embed_batch)

    emb = tier1.Tier1Embedder(index_path=tmp_path / "order.idx")
    n = emb.embed_unprocessed(db, limit=5, db_path=db.db_path, batch_size=2)
    assert n == 5

    # Reopen and confirm: querying with path-i's one-hot vector returns image_id i+1.
    store = tier1.TurboVecStore(dim=1152, bit_width=4, path=tmp_path / "order.idx")
    # ids are 1..5 (autoincrement); path index == id-1.
    for image_id in range(1, 6):
        q = np.zeros(1152, dtype=np.float32)
        q[image_id - 1] = 1.0
        top_id, top_score = store.search(q, k=1)[0]
        assert top_id == image_id, f"id {image_id} mismatched top match {top_id}"


# --------------------------------------------------------------------------- #
# (c) RAGGED final batch — N not divisible by batch_size
# --------------------------------------------------------------------------- #
def test_embed_unprocessed_ragged_final_batch(db, monkeypatch, tmp_path):
    """5 images, batch_size 2 -> chunks of 2,2,1; all 5 embedded."""
    with db.get_session() as s:
        for i in range(5):
            s.add(Image(path=f"r{i}", filename=f"r{i}", file_hash=f"rh{i}"))
        s.commit()

    seen_chunk_sizes = []

    def fake_embed_batch(self, rel_paths):
        seen_chunk_sizes.append(len(rel_paths))
        rows = [np.eye(1152, dtype=np.float32)[hash(rp) % 1152] for rp in rel_paths]
        return np.asarray(rows, dtype=np.float32)

    monkeypatch.setattr(tier1.Tier1Embedder, "embed_images_batched", fake_embed_batch)

    emb = tier1.Tier1Embedder(index_path=tmp_path / "ragged.idx")
    n = emb.embed_unprocessed(db, limit=5, db_path=db.db_path, batch_size=2)

    assert n == 5
    assert seen_chunk_sizes == [2, 2, 1]  # ragged last chunk handled
    store = tier1.TurboVecStore(dim=1152, bit_width=4, path=tmp_path / "ragged.idx")
    assert sum(1 for i in range(1, 6) if store.contains(i)) == 5


# --------------------------------------------------------------------------- #
# (d) CHECKPOINT cadence — mirrors test_tier1_checkpoint.py
# --------------------------------------------------------------------------- #
def test_batched_embed_unprocessed_checkpoints_every_n(db, monkeypatch, tmp_path):
    """5 imgs, checkpoint_every 2 -> saves at 2,4 + final = 3, via batched path."""
    with db.get_session() as s:
        for i in range(5):
            s.add(Image(path=f"c{i}", filename=f"c{i}", file_hash=f"ch{i}"))
        s.commit()

    counter = {"i": 0}

    def fake_embed_batch(self, rel_paths):
        rows = []
        for _ in rel_paths:
            counter["i"] += 1
            v = np.zeros(1152, dtype=np.float32)
            v[counter["i"] % 1152] = 1.0
            rows.append(v)
        return np.asarray(rows, dtype=np.float32)

    monkeypatch.setattr(tier1.Tier1Embedder, "embed_images_batched", fake_embed_batch)

    saves = {"n": 0}
    real_save = tier1.TurboVecStore.save

    def counting_save(self):
        saves["n"] += 1
        return real_save(self)

    monkeypatch.setattr(tier1.TurboVecStore, "save", counting_save)

    emb = tier1.Tier1Embedder(index_path=tmp_path / "cp.idx")
    # batch_size 2 spans the checkpoint boundary; cadence must still be per-N.
    n = emb.embed_unprocessed(
        db, limit=5, db_path=db.db_path, checkpoint_every=2, batch_size=2
    )

    assert n == 5
    assert saves["n"] == 3


# --------------------------------------------------------------------------- #
# (e) PARTIAL PERSISTENCE ON CRASH — checkpointed rows survive a mid-pass crash
# --------------------------------------------------------------------------- #
def test_batched_embed_unprocessed_persists_partial_on_crash(db, monkeypatch, tmp_path):
    """Explode on add #3; the checkpoint at 2 must already be on disk."""
    with db.get_session() as s:
        for i in range(4):
            s.add(Image(path=f"x{i}", filename=f"x{i}", file_hash=f"xh{i}"))
        s.commit()

    def fake_embed_batch(self, rel_paths):
        rows = []
        for rp in rel_paths:
            v = np.zeros(1152, dtype=np.float32)
            v[hash(rp) % 1152] = 1.0
            rows.append(v)
        return np.asarray(rows, dtype=np.float32)

    monkeypatch.setattr(tier1.Tier1Embedder, "embed_images_batched", fake_embed_batch)

    calls = {"n": 0}
    real_add = tier1.TurboVecStore.add

    def exploding_add(self, image_id, vector):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("boom mid-pass")
        return real_add(self, image_id, vector)

    monkeypatch.setattr(tier1.TurboVecStore, "add", exploding_add)

    idx_path = tmp_path / "crash.idx"
    emb = tier1.Tier1Embedder(index_path=idx_path)
    with pytest.raises(RuntimeError):
        emb.embed_unprocessed(
            db, limit=4, db_path=db.db_path, checkpoint_every=2, batch_size=4
        )

    # The first 2 (checkpointed) survive on disk despite the crash at add #3.
    reopened = tier1.TurboVecStore(dim=1152, bit_width=4, path=idx_path)
    n_present = sum(1 for i in (1, 2, 3, 4) if reopened.contains(i))
    assert n_present == 2
