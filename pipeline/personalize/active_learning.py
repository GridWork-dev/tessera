"""
ACTIVE-LEARNING loop (personalization rung 2).

Reuse the human's existing keep/reject signal — ``images.flag_action`` — as the
probe's labels (``keep`` -> positive, ``reject`` -> negative; ``maybe``/NULL are
the UNLABELED pool). Train the rung-1 linear probe on those labels, score the
unlabeled pool, then rank by UNCERTAINTY (smallest ``|margin|`` — the images the
probe is least sure about) to propose the next items a human should label. Most
information gained per label.

Pure ranking — this module NEVER writes. Only images that actually have a stored
SigLIP vector are eligible (an image with no vector cannot be scored).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

# Allow running standalone: put the repo root on sys.path so `pipeline` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pipeline.centroid_tagger import load_vectors_for_ids  # noqa: E402
from pipeline.personalize.probe import fit_linear_probe  # noqa: E402

# images.flag_action values that act as labels for the probe.
KEEP = "keep"
REJECT = "reject"


def _vector_image_ids(db: Any) -> set[int]:
    """Set of image ids that have a stored vector in ``vec_siglip_1152``."""
    from pipeline.centroid_tagger import _connect
    from pipeline.tier1_embedder import VEC_TABLE

    conn = _connect(db)
    try:
        rows = conn.execute(f"SELECT image_id FROM {VEC_TABLE}").fetchall()
    finally:
        conn.close()
    return {int(r[0]) for r in rows}


def _hash_map(db: Any, ids: list[int]) -> dict[int, str | None]:
    """``image_id -> file_hash`` for ``ids`` in ONE query.

    Lets the active-learning queue ship a thumbnail hash with each proposal so
    the UI renders thumbs without a getImageDetail fetch per card (was an N+1).
    """
    if not ids:
        return {}
    from sqlalchemy import select

    from pipeline.database import Image

    with db.get_session() as session:
        rows = session.execute(
            select(Image.id, Image.file_hash).where(Image.id.in_(ids))
        ).all()
    return {int(i): h for i, h in rows}


def load_flag_labels(db: Any) -> tuple[list[int], list[int], list[int]]:
    """Partition image ids by ``flag_action`` into (pos, neg, unlabeled).

    ``keep`` -> positive, ``reject`` -> negative, everything else (NULL,
    ``maybe``, or any other value) -> unlabeled. Only ids that HAVE a stored
    vector are returned (others cannot be scored). Lists are sorted ascending.
    """
    from sqlalchemy import select

    from pipeline.database import Image

    has_vec = _vector_image_ids(db)
    pos: list[int] = []
    neg: list[int] = []
    unlabeled: list[int] = []
    with db.get_session() as session:
        rows = session.execute(select(Image.id, Image.flag_action)).all()
    for image_id, action in rows:
        iid = int(image_id)
        if iid not in has_vec:
            continue
        if action == KEEP:
            pos.append(iid)
        elif action == REJECT:
            neg.append(iid)
        else:
            unlabeled.append(iid)
    return sorted(pos), sorted(neg), sorted(unlabeled)


def propose_next(
    db: Any,
    *,
    count: int = 20,
    l2: float = 1e-2,
    iters: int = 400,
    lr: float = 0.5,
) -> dict[str, Any]:
    """Rank the unlabeled pool by uncertainty; return the next items to label.

    Trains the rung-1 probe on the keep/reject labels and returns the ``count``
    unlabeled images with the smallest ``|margin|`` (most uncertain). Shape::

        {
          "ready": bool,
          "n_pos": int, "n_neg": int, "n_unlabeled": int,
          "proposals": [{"image_id", "probability", "margin"}],
          "reason": str,
        }

    Cold start: if either class is empty there is no boundary to be uncertain
    about, so ``ready=False`` and (when a positive class exists) we fall back to
    the most-confident-positive ordering by centroid cosine so the surface is
    never blank. With no positives at all, ``proposals`` is empty.
    """
    pos_ids, neg_ids, unlabeled_ids = load_flag_labels(db)
    base = {
        "n_pos": len(pos_ids),
        "n_neg": len(neg_ids),
        "n_unlabeled": len(unlabeled_ids),
    }

    if not unlabeled_ids:
        return {
            **base,
            "ready": False,
            "proposals": [],
            "reason": "no unlabeled images",
        }

    pool_matrix = load_vectors_for_ids(db, unlabeled_ids)

    if not pos_ids or not neg_ids:
        # Cold start: no two-class boundary. Fall back to nearest-centroid of
        # whichever class exists (positives preferred) so the queue isn't blank.
        return _cold_start(db, base, pos_ids, unlabeled_ids, pool_matrix, count)

    probe = fit_linear_probe(
        load_vectors_for_ids(db, pos_ids),
        load_vectors_for_ids(db, neg_ids),
        l2=l2,
        iters=iters,
        lr=lr,
    )
    margins = probe.margin(pool_matrix)
    probs = probe.score(pool_matrix)
    # Most uncertain first = smallest |margin|.
    order = np.argsort(np.abs(margins))[: int(count)]
    hashes = _hash_map(db, [int(unlabeled_ids[i]) for i in order])
    proposals = [
        {
            "image_id": int(unlabeled_ids[i]),
            "file_hash": hashes.get(int(unlabeled_ids[i])),
            "probability": float(probs[i]),
            "margin": float(margins[i]),
        }
        for i in order
    ]
    return {**base, "ready": True, "proposals": proposals, "reason": "uncertainty"}


def _cold_start(
    db: Any,
    base: dict[str, Any],
    pos_ids: list[int],
    unlabeled_ids: list[int],
    pool_matrix: np.ndarray,
    count: int,
) -> dict[str, Any]:
    """No two-class boundary yet. Order the pool by centroid cosine if we have
    any positives; otherwise return an empty proposal set (need a label first)."""
    from pipeline.centroid_tagger import compute_centroid, score_all

    if not pos_ids:
        return {
            **base,
            "ready": False,
            "proposals": [],
            "reason": "cold start: label at least one keep and one reject",
        }
    centroid = compute_centroid(load_vectors_for_ids(db, pos_ids))
    cos = score_all(centroid, pool_matrix)
    order = np.argsort(-cos)[: int(count)]
    hashes = _hash_map(db, [int(unlabeled_ids[i]) for i in order])
    proposals = [
        {
            "image_id": int(unlabeled_ids[i]),
            "file_hash": hashes.get(int(unlabeled_ids[i])),
            "probability": float(cos[i]),
            "margin": float(cos[i]),
        }
        for i in order
    ]
    return {
        **base,
        "ready": False,
        "proposals": proposals,
        "reason": "cold start: ranked by similarity to kept exemplars",
    }


__all__ = ["KEEP", "REJECT", "load_flag_labels", "propose_next"]
