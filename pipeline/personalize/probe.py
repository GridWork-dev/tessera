"""
Few-shot LINEAR PROBE over the stored SigLIP image vectors (personalization
rung 1).

Where ``pipeline/centroid_tagger.py`` does a one-class nearest-centroid, this
adds explicit NEGATIVES and a decision boundary: positives + negatives train a
small L2-regularized logistic regression (``w``, ``b``) directly on the stored
1152-dim float32 vectors. numpy-only — no torch, no sklearn, no model load, no
GPU. Reads vectors via the centroid tagger's stable read helpers (we do NOT
edit that module).

Scores are calibrated probabilities in ``[0, 1]``; the signed pre-sigmoid
``margin`` (``X·w + b``) is what the active-learning loop ranks by uncertainty.

Writes go through ``Database.add_tags_scored`` with ``tag_source="probe"``
(idempotent UPSERT). Dry-run is the DEFAULT and writes nothing — the caller must
explicitly pass ``dry_run=False`` to apply. Backup-before-write is the CALLER's
responsibility (same contract as ``centroid_tagger.apply``).
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

# Allow running standalone: put the repo root on sys.path so `pipeline` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pipeline.centroid_tagger import (  # noqa: E402
    EMBEDDING_DIM_DEFAULT,
    load_all_vectors,
    load_vectors_for_ids,
)

logger = logging.getLogger(__name__)

TAG_SOURCE = "probe"


def _sigmoid(z: np.ndarray) -> np.ndarray:
    """Numerically stable logistic sigmoid."""
    out = np.empty_like(z, dtype=np.float64)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out


@dataclass(frozen=True)
class LinearProbe:
    """A trained two-class linear probe over SigLIP vectors.

    ``weights`` is float32[dim], ``bias`` a scalar. ``score`` returns the
    calibrated probability of the positive class; ``margin`` returns the signed
    pre-sigmoid logit (distance from the decision boundary).
    """

    weights: np.ndarray
    bias: float
    dim: int

    def margin(self, matrix: np.ndarray) -> np.ndarray:
        """Signed logit ``X·w + b`` for each row -> float64[N]."""
        mat = np.asarray(matrix, dtype=np.float64)
        if mat.shape[0] == 0:
            return np.empty((0,), dtype=np.float64)
        return mat @ self.weights.astype(np.float64) + self.bias

    def score(self, matrix: np.ndarray) -> np.ndarray:
        """Positive-class probability in ``[0, 1]`` for each row -> float64[N]."""
        return _sigmoid(self.margin(matrix))


def fit_linear_probe(
    pos: np.ndarray,
    neg: np.ndarray,
    *,
    l2: float = 1e-2,
    iters: int = 400,
    lr: float = 0.5,
) -> LinearProbe:
    """Train an L2-regularized logistic regression on (pos=1, neg=0) rows.

    Plain numpy full-batch gradient descent — the corpus is small and 1152-dim
    is cheap, so a few hundred iterations converge sub-second. Raises
    ``ValueError`` if either class is empty (a probe needs both classes; the
    one-class case is what ``centroid_tagger`` already covers).
    """
    p = np.asarray(pos, dtype=np.float64)
    n = np.asarray(neg, dtype=np.float64)
    if p.ndim != 2 or p.shape[0] == 0:
        raise ValueError("fit_linear_probe needs a non-empty positive matrix")
    if n.ndim != 2 or n.shape[0] == 0:
        raise ValueError("fit_linear_probe needs a non-empty negative matrix")
    if p.shape[1] != n.shape[1]:
        raise ValueError(f"pos/neg dim mismatch: {p.shape[1]} != {n.shape[1]}")

    dim = p.shape[1]
    x = np.vstack([p, n])
    y = np.concatenate([np.ones(p.shape[0]), np.zeros(n.shape[0])])
    m = x.shape[0]

    w = np.zeros(dim, dtype=np.float64)
    b = 0.0
    for _ in range(int(iters)):
        preds = _sigmoid(x @ w + b)
        err = preds - y
        grad_w = (x.T @ err) / m + l2 * w
        grad_b = float(err.mean())
        w -= lr * grad_w
        b -= lr * grad_b

    return LinearProbe(weights=w.astype(np.float32), bias=float(b), dim=dim)


def train_probe_from_ids(
    db: Any,
    pos_ids: list[int],
    neg_ids: list[int],
    **fit_kw: Any,
) -> LinearProbe:
    """Load the stored vectors for the two id lists, then fit the probe."""
    pos = load_vectors_for_ids(db, pos_ids)
    neg = load_vectors_for_ids(db, neg_ids)
    return fit_linear_probe(pos, neg, **fit_kw)


def preview(
    db: Any,
    pos_ids: list[int],
    neg_ids: list[int],
    threshold: float = 0.5,
    sample: int = 20,
    **fit_kw: Any,
) -> dict[str, Any]:
    """READ-ONLY: count images scoring > ``threshold`` + a top-scoring sample.

    Returns ``{count, threshold, total, n_pos, n_neg, sample: [(id, prob), ...]}``.
    Never writes.
    """
    probe = train_probe_from_ids(db, pos_ids, neg_ids, **fit_kw)
    ids, matrix = load_all_vectors(db)
    scores = probe.score(matrix)
    above = scores > threshold
    order = np.argsort(-scores)[:sample]
    top = [(int(ids[i]), float(scores[i])) for i in order if scores[i] > threshold]
    return {
        "count": int(above.sum()),
        "threshold": float(threshold),
        "total": int(len(ids)),
        "n_pos": len(pos_ids),
        "n_neg": len(neg_ids),
        "sample": top,
    }


def apply(
    db: Any,
    pos_ids: list[int],
    neg_ids: list[int],
    category: str,
    value: str,
    threshold: float = 0.5,
    confidence: float | None = None,
    dry_run: bool = True,
    **fit_kw: Any,
) -> dict[str, Any]:
    """Tag every image scoring > ``threshold`` with ``(category, value)``.

    Dry-run is the DEFAULT and writes nothing — it returns ``preview(...)``.
    With ``dry_run=False`` each above-threshold image is written via
    ``db.add_tags_scored`` (``tag_source="probe"``, idempotent UPSERT) and the
    returned dict adds ``{"written": <n>, "dry_run": False}``.
    """
    result = preview(db, pos_ids, neg_ids, threshold, **fit_kw)
    if dry_run:
        result["dry_run"] = True
        result["written"] = 0
        return result

    probe = train_probe_from_ids(db, pos_ids, neg_ids, **fit_kw)
    ids, matrix = load_all_vectors(db)
    scores = probe.score(matrix)
    target_ids = [ids[i] for i in range(len(ids)) if scores[i] > threshold]

    written = 0
    with db.get_session() as session:
        for image_id in target_ids:
            db.add_tags_scored(
                session,
                image_id,
                [
                    {
                        "category": category,
                        "value": value,
                        "confidence": confidence,
                        "tag_source": TAG_SOURCE,
                    }
                ],
            )
            written += 1
    result["dry_run"] = False
    result["written"] = written
    logger.info(
        "linear-probe: wrote %s='%s' to %d images (threshold=%.3f)",
        category,
        value,
        written,
        threshold,
    )
    return result


__all__ = [
    "EMBEDDING_DIM_DEFAULT",
    "LinearProbe",
    "TAG_SOURCE",
    "apply",
    "fit_linear_probe",
    "preview",
    "train_probe_from_ids",
]
