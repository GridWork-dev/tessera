"""Zero-shot scene tags that REUSE the existing SigLIP image embeddings.

No new model and no new schema: every image already has a unit 1152-dim SigLIP
vector in ``vec_siglip_1152``. We embed a small fixed scene vocabulary through
the **same SigLIP text tower** (``pipeline.text_embedder``) — so the label
vectors land on the same unit sphere — and score each image by cosine. Labels
clearing a threshold become ``category="scene"`` tag rows.

The scoring (:func:`score_scene_tags`) is pure numpy and needs no model — the
caller passes the precomputed label matrix. Only :func:`embed_labels` touches
the (lazily loaded) text tower, mirroring ``centroid_tagger`` / ``text_embedder``
discipline so the module imports cleanly on a torch-free box.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

TAG_SOURCE = "siglip_zeroshot"
TAG_CATEGORY = "scene"
DEFAULT_THRESHOLD = 0.12  # cosine bar; SigLIP cross-modal scores are small.
DEFAULT_TOP_K = 3

# A small, editable scene vocabulary. The prompt prefix nudges SigLIP toward a
# scene reading; keep it short — towers must match (see siglip-quirks.md).
SCENE_VOCAB: tuple[str, ...] = (
    "a photo of a beach",
    "a photo of mountains",
    "a photo of a forest",
    "a photo of a city street",
    "a photo of the countryside",
    "a photo of a desert",
    "a photo of snow",
    "a photo taken indoors",
    "a photo taken outdoors",
    "a photo of a restaurant",
    "a photo of a party or concert",
    "a photo of the ocean or a lake",
    "a photo of a sunset",
    "a photo of a garden or park",
)

# Short label written to the tag row, parallel to SCENE_VOCAB (the prompt prefix
# stripped). Kept explicit so reworded prompts don't change stored values.
SCENE_LABELS: tuple[str, ...] = (
    "beach",
    "mountains",
    "forest",
    "city street",
    "countryside",
    "desert",
    "snow",
    "indoors",
    "outdoors",
    "restaurant",
    "party",
    "water",
    "sunset",
    "park",
)


def score_scene_tags(
    image_vec: np.ndarray,
    label_mat: np.ndarray,
    labels: list[str] | tuple[str, ...],
    threshold: float = DEFAULT_THRESHOLD,
    top_k: int = DEFAULT_TOP_K,
) -> list[dict[str, Any]]:
    """Cosine-score one image vector against the label matrix.

    ``image_vec`` is a unit ``[1152]`` vector; ``label_mat`` is a unit
    ``[L, 1152]`` matrix (rows aligned to ``labels``). Returns the labels whose
    cosine clears ``threshold``, ordered by descending confidence and capped at
    ``top_k`` — as ``[{"value", "confidence"}]``. Pure numpy, no model load.
    """
    vec = np.asarray(image_vec, dtype=np.float32).ravel()
    mat = np.asarray(label_mat, dtype=np.float32)
    if vec.size == 0 or mat.size == 0:
        return []
    if mat.shape[1] != vec.shape[0]:
        raise ValueError(
            f"label_mat dim {mat.shape[1]} != image_vec dim {vec.shape[0]}"
        )
    sims = mat @ vec  # both unit-normalized -> cosine
    order = np.argsort(-sims)
    out: list[dict[str, Any]] = []
    for idx in order:
        score = float(sims[idx])
        if score < threshold:
            break  # sorted desc — nothing past here clears the bar
        out.append({"value": labels[int(idx)], "confidence": score})
        if len(out) >= top_k:
            break
    return out


def embed_labels(prompts: list[str] | tuple[str, ...] = SCENE_VOCAB) -> np.ndarray:
    """Embed the scene prompts through the SigLIP text tower -> unit ``[L,1152]``.

    Reuses ``pipeline.text_embedder.embed_text`` (the query-side twin of the
    image embedder), so the label vectors share the image vectors' unit sphere.
    Loads the model lazily on first call — guard the caller with torch
    availability. CPU-fine for the ~14-label vocabulary.
    """
    from pipeline.text_embedder import embed_text  # lazy: torch/transformers

    rows = [embed_text(p) for p in prompts]
    return np.vstack(rows).astype(np.float32)
