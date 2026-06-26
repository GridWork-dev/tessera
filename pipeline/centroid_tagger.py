"""
Few-shot nearest-centroid tagger over the stored SigLIP image vectors.

Given a handful of exemplar image ids that share a visual concept, average
their (unit) SigLIP vectors into a centroid, then score every indexed image by
cosine to that centroid and (optionally) write a tag to the images above a
threshold. numpy-only — no new dependencies, no model load. Reads the float32
blobs straight out of the ``vec_siglip_1152`` sqlite-vec table (the same store
``webui/search.py`` rescores against).

Writes go through ``Database.add_tags_scored`` with ``tag_source="centroid"``
(idempotent UPSERT). Dry-run is the DEFAULT and writes nothing — the caller
must explicitly pass ``dry_run=False`` to apply. Backup-before-write is the
CALLER's responsibility.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any

import numpy as np

# Allow running as a script (python pipeline/centroid_tagger.py): put the repo
# root on sys.path so the `pipeline` package imports resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.tier1_embedder import VEC_TABLE, Tier1Embedder, l2_normalize  # noqa: E402

logger = logging.getLogger(__name__)

TAG_SOURCE = "centroid"
EMBEDDING_DIM_DEFAULT = Tier1Embedder.EMBEDDING_DIM


def _deserialize(blob: bytes) -> np.ndarray:
    """Decode a raw float32 sqlite-vec blob into a 1-D float32 vector."""
    return np.frombuffer(blob, dtype=np.float32)


def _connect(db: Any) -> sqlite3.Connection:
    """Open the vec store via tier1's loader (sqlite-vec extension loaded)."""
    from pipeline.tier1_embedder import open_vec_db

    return open_vec_db(db.db_path)


def load_all_vectors(db: Any) -> tuple[list[int], np.ndarray]:
    """Read every (image_id, embedding) from ``vec_siglip_1152``.

    Returns ``(ids, matrix)`` where ``matrix`` is float32 ``[N, 1152]`` and
    ``ids[i]`` is the image id of row ``i``. Empty store -> empty matrix.
    """
    conn = _connect(db)
    try:
        rows = conn.execute(
            f"SELECT image_id, embedding FROM {VEC_TABLE} ORDER BY image_id"
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return [], np.empty((0, EMBEDDING_DIM_DEFAULT), dtype=np.float32)
    ids = [int(r[0]) for r in rows]
    matrix = np.vstack([_deserialize(r[1]) for r in rows]).astype(np.float32)
    return ids, matrix


def load_vectors_for_ids(db: Any, ids: list[int]) -> np.ndarray:
    """Load the float32 vectors for ``ids`` (order preserved, missing skipped)."""
    if not ids:
        return np.empty((0, EMBEDDING_DIM_DEFAULT), dtype=np.float32)
    conn = _connect(db)
    try:
        found: dict[int, np.ndarray] = {}
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"SELECT image_id, embedding FROM {VEC_TABLE} "
            f"WHERE image_id IN ({placeholders})",
            [int(i) for i in ids],
        ).fetchall()
        for image_id, blob in rows:
            found[int(image_id)] = _deserialize(blob)
    finally:
        conn.close()
    ordered = [found[i] for i in ids if i in found]
    if not ordered:
        return np.empty((0, EMBEDDING_DIM_DEFAULT), dtype=np.float32)
    return np.vstack(ordered).astype(np.float32)


def compute_centroid(vectors: np.ndarray) -> np.ndarray:
    """L2-normalized mean of the exemplar vectors -> unit float32[1152]."""
    mat = np.asarray(vectors, dtype=np.float32)
    if mat.ndim != 2 or mat.shape[0] == 0:
        raise ValueError("compute_centroid needs a non-empty [N, dim] matrix")
    mean = mat.mean(axis=0)
    return l2_normalize(mean)


def score_all(centroid: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine of each row in ``matrix`` to ``centroid`` -> float32[N].

    Both centroid and stored vectors are unit-norm, so cosine == dot product.
    """
    c = np.asarray(centroid, dtype=np.float32).ravel()
    mat = np.asarray(matrix, dtype=np.float32)
    if mat.shape[0] == 0:
        return np.empty((0,), dtype=np.float32)
    return (mat @ c).astype(np.float32)


def preview(
    db: Any,
    exemplar_ids: list[int],
    threshold: float,
    sample: int = 20,
) -> dict[str, Any]:
    """READ-ONLY: count images scoring > ``threshold`` + a top-scoring sample.

    Returns ``{count, threshold, total, sample: [(image_id, score), ...]}``.
    Never writes.
    """
    centroid = compute_centroid(load_vectors_for_ids(db, exemplar_ids))
    ids, matrix = load_all_vectors(db)
    scores = score_all(centroid, matrix)
    above = scores > threshold
    count = int(above.sum())
    # Top-scoring sample (best-first), capped at ``sample``.
    order = np.argsort(-scores)[:sample]
    top = [(int(ids[i]), float(scores[i])) for i in order if scores[i] > threshold]
    return {
        "count": count,
        "threshold": float(threshold),
        "total": int(len(ids)),
        "sample": top,
    }


def apply(
    db: Any,
    exemplar_ids: list[int],
    category: str,
    value: str,
    threshold: float,
    confidence: float | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Tag every image scoring > ``threshold`` with ``(category, value)``.

    Dry-run is the DEFAULT and writes nothing — it returns ``preview(...)``.
    With ``dry_run=False`` each above-threshold image is written via
    ``db.add_tags_scored`` (``tag_source="centroid"``, idempotent UPSERT) and
    the returned dict adds ``{"written": <n>, "dry_run": False}``.
    """
    result = preview(db, exemplar_ids, threshold)
    if dry_run:
        result["dry_run"] = True
        result["written"] = 0
        return result

    centroid = compute_centroid(load_vectors_for_ids(db, exemplar_ids))
    ids, matrix = load_all_vectors(db)
    scores = score_all(centroid, matrix)
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
        "centroid-tag: wrote %s='%s' to %d images (threshold=%.3f)",
        category,
        value,
        written,
        threshold,
    )
    return result


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Few-shot nearest-centroid tagger over SigLIP vectors "
        "(dry-run by default).",
    )
    parser.add_argument(
        "--exemplars",
        required=True,
        help="Comma-separated exemplar image ids (e.g. 12,34,56).",
    )
    parser.add_argument("--category", required=True)
    parser.add_argument("--value", required=True)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--confidence", type=float, default=None)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write tags. Omit for a read-only dry-run (default).",
    )
    args = parser.parse_args(argv)

    from pipeline.database import Database
    from pipeline.paths import REPO_ROOT

    exemplar_ids = [int(x) for x in args.exemplars.split(",") if x.strip()]
    db = Database(str(REPO_ROOT / "data" / "catalog.db"))
    result = apply(
        db,
        exemplar_ids,
        category=args.category,
        value=args.value,
        threshold=args.threshold,
        confidence=args.confidence,
        dry_run=not args.apply,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
