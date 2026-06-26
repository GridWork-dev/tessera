"""Tests for the SigLIP text tower (ADR-0006).

The pure tests run everywhere. The live test loads ~1GB of SigLIP weights and
is skipped unless the model can actually be constructed — it must NOT break
collection when torch/transformers/weights are unavailable.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from pipeline import text_embedder as te


def test_module_constants_match_image_side():
    # The text tower MUST share the image checkpoint + dim (same unit sphere).
    from pipeline.tier1_embedder import Tier1Embedder

    assert te.MODEL_ID == Tier1Embedder.MODEL_ID
    assert te.EMBEDDING_DIM == Tier1Embedder.EMBEDDING_DIM == 1152
    assert te.MAX_LENGTH == 64


def test_reuses_image_side_l2_normalize():
    # ADR-0006: the text vector must use the SAME l2_normalize as the image path.
    from pipeline.tier1_embedder import l2_normalize

    assert te.l2_normalize is l2_normalize
    out = te.l2_normalize(np.array([3.0, 4.0], dtype=np.float32))
    assert np.linalg.norm(out) == pytest.approx(1.0, abs=1e-6)
    assert out.dtype == np.float32


def test_singleton_is_stable():
    a = te.get_text_embedder()
    b = te.get_text_embedder()
    assert a is b


def _model_loadable() -> bool:
    """True only if SigLIP weights can be constructed quickly enough to test."""
    if os.environ.get("SKIP_LIVE_MODEL_TESTS"):
        return False
    try:
        emb = te.TextEmbedder()
        emb._load()
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _model_loadable(),
    reason="SigLIP text-tower weights/torch unavailable (live test guarded)",
)
def test_embed_text_live_contract():
    emb = te.TextEmbedder()
    emb._load()

    # ADR acceptance 2: the processor honors padding='max_length', max_length=64.
    inputs = emb.processor(
        text=["a photo"],
        padding="max_length",
        max_length=te.MAX_LENGTH,
        truncation=True,
        return_tensors="pt",
    )
    assert inputs["input_ids"].shape[-1] == 64

    # ADR acceptance 1: (1152,), unit-norm.
    vec = te.embed_text("a photo")
    assert vec.shape == (1152,)
    assert vec.dtype == np.float32
    assert float(np.linalg.norm(vec)) == pytest.approx(1.0, abs=1e-3)
