"""
SigLIP SO400M *text tower* — the query-side twin of ``tier1_embedder.py``.

Embeds free-text queries into the SAME 1152-dim unit sphere as the stored
image vectors (``vec_siglip_1152`` / ``data/turbovec_siglip.idx``), so a text
query can rank images by cross-modal cosine. Implements ADR-0006 exactly:
in-process, lazy-loaded, single ``threading.Lock``-guarded forward, and the
NON-NEGOTIABLE ``padding="max_length", max_length=64`` preprocessing contract.

Heavy deps (torch / transformers) are imported lazily inside ``_load`` — the
MacBook venv may lack them at import time, so the module imports cleanly and its
pure tests run without a model. ``l2_normalize`` is reused from
``tier1_embedder`` so the text vector lands on the same sphere the cosine
rescore expects — do NOT reimplement it here.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import numpy as np

from pipeline.tier1_embedder import l2_normalize

logger = logging.getLogger(__name__)

MODEL_ID = "google/siglip-so400m-patch14-384"  # identical to the image side
EMBEDDING_DIM = 1152
MAX_LENGTH = 64  # SigLIP text context length — MANDATORY per ADR-0006 section 2

# The model is NOT thread-safe across concurrent forwards. A single user won't
# contend, but guard the forward so the in-process choice is safe under the
# default multi-route server.
_FORWARD_LOCK = threading.Lock()


class TextEmbedder:
    """SigLIP SO400M text tower -> L2-normalized float32[1152] query vectors.

    Mirrors ``Tier1Embedder._load`` exactly: torch + transformers imported
    lazily, device = mps-or-cpu, ``AutoProcessor`` / ``AutoModel`` ``.eval()``.
    Loaded on first call and cached for process lifetime.
    """

    MODEL_ID = MODEL_ID
    EMBEDDING_DIM = EMBEDDING_DIM

    def __init__(self) -> None:
        self.processor: Any = None
        self.model: Any = None
        self.device: Any = None

    def _load(self) -> None:
        """Lazily import torch + transformers and load SigLIP onto mps-or-cpu."""
        if self.model is not None:
            return
        import torch  # lazy: MacBook venv may have no torch
        from transformers import AutoModel, AutoProcessor

        self.device = (
            torch.device("mps")
            if torch.backends.mps.is_available()
            else torch.device("cpu")
        )
        logger.info("Loading %s (text tower) on %s ...", self.MODEL_ID, self.device)
        self.processor = AutoProcessor.from_pretrained(self.MODEL_ID)
        self.model = AutoModel.from_pretrained(self.MODEL_ID).to(self.device).eval()

    def embed_text(self, q: str) -> np.ndarray:
        """Embed a free-text query -> L2-normalized float32[1152].

        ``padding="max_length"`` and ``max_length=64`` are MANDATORY per
        ADR-0006 section 2 — the model was trained that way and the default
        ``padding="longest"`` silently poisons every query. Case normalization
        is owned by ``SiglipTokenizer`` (do NOT pre-lowercase here).
        """
        import torch  # lazy

        self._load()
        inputs = self.processor(
            text=[q],
            padding="max_length",
            max_length=MAX_LENGTH,
            truncation=True,
            return_tensors="pt",
        ).to(self.device)
        with _FORWARD_LOCK, torch.no_grad():
            out = self.model.get_text_features(**inputs)
        # transformers 5.x returns a BaseModelOutputWithPooling here (symmetric
        # with the image side's get_image_features). Read .pooler_output -> the
        # pooled (1, 1152) vector, NOT the (1, 64, 1152) last_hidden_state. The
        # ADR-0006 snippet's bare-tensor `feats[0]` predates this API.
        pooled = out.pooler_output  # (1, 1152)
        return l2_normalize(pooled[0].cpu().numpy().astype(np.float32))


_SINGLETON: TextEmbedder | None = None
_SINGLETON_LOCK = threading.Lock()


def get_text_embedder() -> TextEmbedder:
    """Process-lifetime singleton ``TextEmbedder`` (created on first use)."""
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = TextEmbedder()
    return _SINGLETON


def embed_text(q: str) -> np.ndarray:
    """Embed a free-text query via the singleton text tower -> float32[1152].

    This is the exact symbol ``webui/search.py`` imports.
    """
    return get_text_embedder().embed_text(q)
