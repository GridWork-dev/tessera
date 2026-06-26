"""LAION-style linear aesthetic head over SigLIP 1152-dim image embeddings (Wave 4).

A *tiny* linear model that turns an already-computed SigLIP SO400M image
embedding (the 1152-dim ``pooler_output`` from ``pipeline/tier1_embedder.py``)
into a single "how attractive is this frame" score. This is the
``LAION-aesthetic``-style upgrade called for in
``docs/superpowers/specs/2026-06-25-platform-customization-overhaul-design.md``
§3.7: at trivial extra cost it lets the video best-thumbnail picker prefer
*actually attractive* frames over merely sharp/colorful ones.

NumPy only — no torch, no transformers. The head is just::

    s = sigmoid(w . l2norm(x) + b)          # one score per embedding

so a forward pass over a handful of candidate frames is microseconds.

Weights format (``models/aesthetic_siglip.npz``)
------------------------------------------------
A NumPy ``.npz`` archive with exactly two arrays:

* ``w`` — float, shape ``(1152,)``   the linear weight vector
* ``b`` — float, scalar (shape ``()`` or ``(1,)``)   the bias

Save one with::

    import numpy as np
    np.savez("models/aesthetic_siglip.npz", w=w.astype("float32"),
             b=np.float32(b))

The score is ``sigmoid(w . xhat + b)`` where ``xhat`` is the L2-normalized
embedding, so it always lands in ``(0, 1)`` and blends cleanly with the
[0, 1]-ish OpenCV composite in ``video_thumbnail.py``.

Training the head (NOT done here — just documented)
---------------------------------------------------
The head is a logistic regression on frozen SigLIP embeddings, so training is
cheap and offline:

1. Collect rated examples: image (or video frame) -> a label. Either a binary
   "good poster / bad poster" flag, or a 1-10 LAION-style aesthetic rating
   squashed to [0, 1].
2. Embed each example with ``pipeline.tier1_embedder.Tier1Embedder.embed_image``
   (or ``embed_images_batched``) to get L2-normalized 1152-dim vectors ``X``.
3. Fit a logistic regression (e.g. ``sklearn.linear_model.LogisticRegression``,
   ``C`` tuned by CV) mapping ``X -> label``. For a continuous rating, fit a
   linear regression and either keep it linear or wrap in a sigmoid.
4. Export ``w = clf.coef_.ravel().astype("float32")`` and
   ``b = float(clf.intercept_[0])`` to ``models/aesthetic_siglip.npz`` (above).

Because the embeddings are frozen and L2-normalized, ~a few hundred labelled
examples already give a usable head; the existing OpenCV composite remains the
safety net (the head is *blended*, never the sole signal).

Graceful degradation
---------------------
``load_aesthetic_head()`` returns ``None`` when the weights file is absent or
malformed. Callers treat ``None`` as "feature off" and fall back to the
composite scorer unchanged — the head NEVER hard-fails the poster pipeline.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from pipeline.settings import get_settings

logger = logging.getLogger(__name__)

# Default weights location, under the resolved models dir (settings.models_cache_dir,
# defaults to the repo ``models/``). Kept lazy via _default_weights_path() so tests
# and a frozen bundle resolve it at call time, not import time.
WEIGHTS_FILENAME = "aesthetic_siglip.npz"

EMBEDDING_DIM = 1152  # SigLIP SO400M pooler_output dim (matches Tier1Embedder).


def _default_weights_path() -> Path:
    """Resolve the default weights path under the configured models dir."""
    models_dir = get_settings().models_cache_dir
    return Path(models_dir) / WEIGHTS_FILENAME


class AestheticHead:
    """A frozen linear+sigmoid head over L2-normalized SigLIP embeddings.

    ``score(embeddings)`` accepts a single ``(1152,)`` vector or an ``(n, 1152)``
    batch and returns a float ``(n,)`` array of scores in ``(0, 1)``. The input
    embeddings are L2-normalized internally (idempotent if already normalized),
    so callers may pass raw or normalized vectors interchangeably.
    """

    __slots__ = ("w", "b")

    def __init__(self, w: np.ndarray, b: float) -> None:
        w = np.asarray(w, dtype=np.float32).ravel()
        if w.shape != (EMBEDDING_DIM,):
            raise ValueError(
                f"aesthetic head weight must be shape ({EMBEDDING_DIM},), got {w.shape}"
            )
        self.w = w
        self.b = float(b)

    def score(self, embeddings: np.ndarray) -> np.ndarray:
        """Score one or many embeddings -> float32 ``(n,)`` in (0, 1).

        L2-normalizes each row first (matching how the head was trained), then
        applies ``sigmoid(w . xhat + b)``. A 1-D input is treated as a single
        row and still returns a length-1 array.
        """
        x = np.asarray(embeddings, dtype=np.float32)
        if x.ndim == 1:
            x = x.reshape(1, -1)
        if x.shape[1] != EMBEDDING_DIM:
            raise ValueError(
                f"embeddings must have {EMBEDDING_DIM} columns, got {x.shape[1]}"
            )
        # Per-row L2 normalize (safe on zero rows -> left as zeros).
        norms = np.linalg.norm(x, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        xhat = x / norms
        logits = xhat @ self.w + self.b
        # Numerically stable logistic sigmoid.
        return _sigmoid(logits).astype(np.float32)


def _sigmoid(z: np.ndarray) -> np.ndarray:
    """Numerically stable elementwise logistic sigmoid."""
    z = np.asarray(z, dtype=np.float64)
    out = np.empty_like(z)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out


def load_aesthetic_head(weights_path: str | Path | None = None) -> AestheticHead | None:
    """Load the linear head from an ``.npz`` weights file, or ``None`` if absent.

    Returns ``None`` (never raises) when the file is missing or malformed, so
    callers fall back to their existing scorer. ``weights_path`` defaults to
    ``<models_cache_dir>/aesthetic_siglip.npz``.
    """
    path = Path(weights_path) if weights_path is not None else _default_weights_path()
    if not path.is_file():
        logger.debug("aesthetic head weights absent at %s — feature off", path)
        return None
    try:
        with np.load(path) as data:
            if "w" not in data or "b" not in data:
                logger.warning(
                    "aesthetic head weights %s missing 'w'/'b' arrays — ignoring",
                    path,
                )
                return None
            w = np.asarray(data["w"], dtype=np.float32)
            b = float(np.asarray(data["b"], dtype=np.float32).ravel()[0])
        return AestheticHead(w, b)
    except Exception as exc:  # noqa: BLE001 - never let a bad file break the pipeline
        logger.warning("failed to load aesthetic head %s: %s — ignoring", path, exc)
        return None
