"""
B4 — Tier-1 embed pass must checkpoint periodically, not only at the end.

The prior pass wrote the .idx + committed the vec table ONCE after the whole
loop, so a crash discarded everything embedded so far. embed_unprocessed must
save the turbovec index + commit the vec table every `checkpoint_every`
embeddings. Tested with a stubbed embed_image (no SigLIP / GPU load).
"""

import numpy as np
import pytest

tier1 = pytest.importorskip("pipeline.tier1_embedder")
pytest.importorskip("turbovec")
pytest.importorskip("sqlite_vec")

from pipeline.database import Image  # noqa: E402


def test_embed_unprocessed_checkpoints_every_n(db, monkeypatch, tmp_path):
    # 5 unembedded images in the catalog.
    with db.get_session() as s:
        for i in range(5):
            s.add(Image(path=f"img{i}", filename=f"img{i}", file_hash=f"h{i}"))
        s.commit()

    # Stub the model so no GPU/SigLIP load happens; distinct unit vectors per id.
    # embed_unprocessed now drives the BATCHED primitive, so stub that.
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

    # Count index saves (the checkpoint signal).
    saves = {"n": 0}
    real_save = tier1.TurboVecStore.save

    def counting_save(self):
        saves["n"] += 1
        return real_save(self)

    monkeypatch.setattr(tier1.TurboVecStore, "save", counting_save)

    emb = tier1.Tier1Embedder(index_path=tmp_path / "x.idx")
    n = emb.embed_unprocessed(db, limit=5, db_path=db.db_path, checkpoint_every=2)

    assert n == 5
    # checkpoints at embedded==2 and ==4, plus one final save == 3.
    assert saves["n"] == 3


def test_embed_unprocessed_persists_partial_on_checkpoint(db, monkeypatch, tmp_path):
    """After a mid-loop checkpoint, the .idx on disk already contains rows."""
    with db.get_session() as s:
        for i in range(4):
            s.add(Image(path=f"p{i}", filename=f"p{i}", file_hash=f"k{i}"))
        s.commit()

    def fake_embed_batch(self, rel_paths):
        rows = []
        for rel_path in rel_paths:
            v = np.zeros(1152, dtype=np.float32)
            v[hash(rel_path) % 1152] = 1.0
            rows.append(v)
        return np.asarray(rows, dtype=np.float32)

    monkeypatch.setattr(tier1.Tier1Embedder, "embed_images_batched", fake_embed_batch)

    # Raise after the 3rd embed — but the checkpoint at 2 must already be on disk.
    calls = {"n": 0}
    real_add = tier1.TurboVecStore.add

    def exploding_add(self, image_id, vector):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("boom mid-pass")
        return real_add(self, image_id, vector)

    monkeypatch.setattr(tier1.TurboVecStore, "add", exploding_add)

    idx_path = tmp_path / "y.idx"
    emb = tier1.Tier1Embedder(index_path=idx_path)
    with pytest.raises(RuntimeError):
        emb.embed_unprocessed(db, limit=4, db_path=db.db_path, checkpoint_every=2)

    # The first 2 (checkpointed) survive on disk despite the crash at #3.
    reopened = tier1.TurboVecStore(dim=1152, bit_width=4, path=idx_path)
    n_present = sum(1 for i in (1, 2, 3, 4) if reopened.contains(i))
    assert n_present == 2
