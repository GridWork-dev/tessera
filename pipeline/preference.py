"""
Track 5 — preference linear probe + few-shot centroid (degrade-first).

Turns the operator's keep/reject flags (``images.flag_action``) into a learned
"more like this" ranking over the SigLIP image vectors. Per the next-phase
roadmap (Bucket B), the probe needs ~100 keep + ~100 reject labels AND landed
image vectors before it can train. Image vectors are now present (full corpus),
so ``centroid_preview`` runs; the probe paths (train / ranked / edge-cases) still
DEGRADE with real counts until the label corpus reaches ``MIN_PER_CLASS`` (today
~34 keep / ~38 reject). No entry point ever fabricates a score.

Design constraints (verified):
  * ``sklearn`` is NOT installed on this Py-3.14 box. The fit is numpy closed-form
    only (ridge-regularized least squares). ``numpy`` IS present.
  * threshold-shift, NOT ``class_weight=balanced``: the decision point is the
    midpoint between the per-class mean margins (prior-aware), so a lopsided
    label count does not bias the boundary.
  * Read-only. Centroid preview is count-vs-threshold only — NO writes. Any
    eventual ``tag_source='centroid'`` write is the caller's job, behind a backup.

The numerical core (``_fit_probe`` / ``_probe_margin`` / ``_centroid``) is pure
(numpy arrays in, numpy out) so it is unit-tested without a DB or real vectors;
the DB-coupled wrappers load vectors from vec_siglip_1152 and stay degrade-gated.

Heavy / situational imports (numpy, the vec store) are lazy so importing this
module is cheap and torch-free.
"""

from __future__ import annotations

from typing import Any

# Roadmap Bucket B thresholds. Both classes need ~100 labels before a 1152-dim
# linear probe is anything but noise.
MIN_PER_CLASS = 100

# Vector/prior blend for the eventual probe score (roadmap: 0.7/0.3). Applied as
# a constant shift on probabilities, so it does NOT change rankings — kept here as
# the documented blend for any future absolute-probability surface.
VECTOR_WEIGHT = 0.7
PRIOR_WEIGHT = 0.3

# Ridge regularization strength for the closed-form probe fit (numpy only).
PROBE_RIDGE_LAMBDA = 1.0

# Reason codes returned in the degrade payloads (stable strings for callers/UI).
REASON_INSUFFICIENT_LABELS = "insufficient_labels"
REASON_VECTORS_UNAVAILABLE = "vectors_unavailable"

# A centroid preview scores the whole corpus, so it needs near-full vector
# coverage to be honest — not just the handful of baseline vectors. Mirror the
# self-retrieval gate's coverage notion (90% of the image corpus).
CORPUS_COVERAGE_FRACTION = 0.90


def _flag_counts(db) -> dict[str, int]:
    """Real keep/reject/maybe counts from ``images.flag_action``."""
    from sqlalchemy import func

    from pipeline.database import Image

    counts = {"keep": 0, "reject": 0, "maybe": 0}
    with db.get_session() as session:
        rows = (
            session.query(Image.flag_action, func.count(Image.id))
            .filter(Image.flag_action.isnot(None))
            .group_by(Image.flag_action)
            .all()
        )
        for action, n in rows:
            if action in counts:
                counts[action] = int(n)
    return counts


def _has_corpus_coverage(db) -> bool:
    """True iff vec_siglip_1152 covers ~the whole image corpus (full run landed).

    Returns False on any error / empty corpus.
    """
    from sqlalchemy import func

    from pipeline.database import Image
    from webui.search import vector_count

    vectors = int(vector_count(db))
    with db.get_session() as session:
        total = int(session.query(func.count(Image.id)).scalar() or 0)
    if total <= 0:
        return False
    return vectors >= int(CORPUS_COVERAGE_FRACTION * total)


def preference_status(db) -> dict[str, Any]:
    """Real readiness snapshot for the preference probe — no fabrication.

    Returns the live keep/reject/maybe label counts, the vector count, the
    per-class minimum, whether the probe is trainable, and (when not) WHY.

    ``trainable`` iff keep >= MIN_PER_CLASS and reject >= MIN_PER_CLASS and
    vectors > 0. When not trainable, ``reason`` is:
      * ``insufficient_labels`` when the label corpus is the binding gap, OR
      * ``vectors_unavailable`` when labels suffice but no vectors exist.
    Labels are the binding constraint, so a label gap wins the reason even when
    vectors are also 0 (the roadmap's "blocked on behavior" framing).
    """
    from webui.search import vector_count

    counts = _flag_counts(db)
    vectors = int(vector_count(db))
    labels_ok = counts["keep"] >= MIN_PER_CLASS and counts["reject"] >= MIN_PER_CLASS
    trainable = labels_ok and vectors > 0

    reason: str | None = None
    if not trainable:
        # Labels are the binding constraint — report the label gap first even if
        # vectors are also missing.
        reason = (
            REASON_INSUFFICIENT_LABELS if not labels_ok else REASON_VECTORS_UNAVAILABLE
        )

    return {
        "keep": counts["keep"],
        "reject": counts["reject"],
        "maybe": counts["maybe"],
        "vectors": vectors,
        "min_per_class": MIN_PER_CLASS,
        "trainable": trainable,
        "reason": reason,
    }


# --- pure numerical core (numpy in / numpy out; no DB) ------------------------


def _l2_normalize_rows(mat):
    """Row-wise L2 normalize a (n, d) matrix; zero rows stay zero (no div-by-0)."""
    import numpy as np

    mat = np.asarray(mat, dtype=np.float64)
    if mat.ndim != 2:
        mat = mat.reshape(1, -1)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def _fit_probe(X, y, lam: float = PROBE_RIDGE_LAMBDA):
    """Ridge-regularized least-squares linear probe on +/-1 targets (numpy only).

    ``X`` (n, d) features, ``y`` (n,) in {0, 1}. Solves the closed form
    ``w = (XaᵀXa + λI)⁻¹ Xaᵀ t`` with t = 2y-1 and a non-penalized bias column.
    Returns ``(w (d,), b (float), threshold (float))`` where the decision
    threshold on the margin is the midpoint of the per-class mean margins
    (threshold-shift; prior-aware without class_weight). NEVER calls sklearn.
    """
    import numpy as np

    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n, d = X.shape
    t = 2.0 * y - 1.0  # {-1, +1}
    Xa = np.hstack([X, np.ones((n, 1))])
    reg = lam * np.eye(d + 1)
    reg[-1, -1] = 0.0  # do not regularize the bias
    coef = np.linalg.solve(Xa.T @ Xa + reg, Xa.T @ t)
    w = coef[:-1].astype(np.float64)
    b = float(coef[-1])
    margins = X @ w + b
    pos_m = float(margins[y == 1].mean()) if np.any(y == 1) else 0.0
    neg_m = float(margins[y == 0].mean()) if np.any(y == 0) else 0.0
    threshold = (pos_m + neg_m) / 2.0
    return w, b, threshold


def _probe_margin(X, w, b):
    """Signed margin X·w + b for each row (higher = more 'keep-like')."""
    import numpy as np

    return np.asarray(X, dtype=np.float64) @ np.asarray(w, dtype=np.float64) + b


def _centroid(pos_mat, neg_mat=None):
    """Nearest-centroid direction: L2-normed mean of positives, minus negatives.

    Returns a unit (d,) vector. With negatives, subtract their unit centroid and
    re-normalize so cosine against it is a positive-vs-negative contrast.
    """
    import numpy as np

    pos_mat = np.asarray(pos_mat, dtype=np.float64)
    c = pos_mat.mean(axis=0)
    c = c / (float(np.linalg.norm(c)) or 1.0)
    if neg_mat is not None and len(neg_mat):
        nc = np.asarray(neg_mat, dtype=np.float64).mean(axis=0)
        nc = nc / (float(np.linalg.norm(nc)) or 1.0)
        c = c - nc
        c = c / (float(np.linalg.norm(c)) or 1.0)
    return c


# --- vec-store loaders (DB-coupled; degrade-gated by callers) -----------------


def _vectors_for_ids(db, image_ids: list[int]) -> tuple[Any, list[int]]:
    """Load vectors for ``image_ids`` from vec_siglip_1152.

    Returns (matrix (k,1152) float32, ids_found). ids missing from the vec store
    are simply absent from ``ids_found`` — the caller decides if that's fatal.
    Returns (None, []) on any vec-store error (missing table / extension).
    """
    import numpy as np

    from pipeline.tier1_embedder import VEC_TABLE, open_vec_db

    conn = None
    rows_found: list[tuple[int, bytes]] = []
    try:
        conn = open_vec_db(db.db_path)
        for image_id in image_ids:
            row = conn.execute(
                f"SELECT embedding FROM {VEC_TABLE} WHERE image_id = ?",
                (int(image_id),),
            ).fetchone()
            if row is not None and row[0] is not None:
                rows_found.append((int(image_id), row[0]))
    except Exception:
        return None, []
    finally:
        if conn is not None:
            conn.close()

    if not rows_found:
        return np.empty((0, 1152), dtype=np.float32), []
    ids_found = [i for i, _ in rows_found]
    mat = np.stack([np.frombuffer(blob, dtype=np.float32) for _, blob in rows_found])
    return mat.astype(np.float32), ids_found


def _all_corpus_vectors(db) -> tuple[list[int], Any]:
    """Load every (image_id, vector) from vec_siglip_1152.

    Returns ``(ids, matrix (N,1152) float32)``. Returns ([], None) on any vec-store
    error so callers degrade rather than raise.
    """
    import numpy as np

    from pipeline.tier1_embedder import VEC_TABLE, open_vec_db

    conn = None
    try:
        conn = open_vec_db(db.db_path)
        rows = conn.execute(f"SELECT image_id, embedding FROM {VEC_TABLE}").fetchall()
    except Exception:
        return [], None
    finally:
        if conn is not None:
            conn.close()

    if not rows:
        return [], np.empty((0, 1152), dtype=np.float32)
    ids = [int(r[0]) for r in rows]
    mat = np.stack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
    return ids, mat.astype(np.float32)


def _labeled_ids(db) -> tuple[list[int], list[int]]:
    """(keep_ids, reject_ids) from ``images.flag_action``."""
    from pipeline.database import Image

    keep: list[int] = []
    reject: list[int] = []
    with db.get_session() as session:
        rows = (
            session.query(Image.id, Image.flag_action)
            .filter(Image.flag_action.in_(("keep", "reject")))
            .all()
        )
        for iid, action in rows:
            (keep if action == "keep" else reject).append(int(iid))
    return keep, reject


def _load_labeled_vectors(db):
    """Stack keep(+1)/reject(0) vectors. Returns (X, y, n_pos, n_neg).

    (None, None, n_pos, n_neg) when either class has no stored vectors — the
    caller degrades to ``vectors_unavailable``.
    """
    import numpy as np

    keep, reject = _labeled_ids(db)
    kmat, kfound = _vectors_for_ids(db, keep)
    rmat, rfound = _vectors_for_ids(db, reject)
    if kmat is None or rmat is None:
        return None, None, 0, 0
    if len(kfound) == 0 or len(rfound) == 0:
        return None, None, len(kfound), len(rfound)
    X = np.vstack([kmat, rmat]).astype(np.float64)
    y = np.concatenate([np.ones(len(kfound)), np.zeros(len(rfound))])
    return X, y, len(kfound), len(rfound)


def _train_probe_model(db) -> dict[str, Any] | None:
    """Fit the probe on the live labels+vectors. None when not trainable.

    Returns ``{w, b, threshold, n_pos, n_neg, accuracy, dim}`` (w as a numpy
    array). Separated from the public ``train_probe`` so the ranking feeds can
    reuse the model without re-serializing weights.
    """
    import numpy as np

    if not preference_status(db)["trainable"]:
        return None
    X, y, n_pos, n_neg = _load_labeled_vectors(db)
    if X is None or len(np.unique(y)) < 2:
        return None
    Xn = _l2_normalize_rows(X)
    w, b, threshold = _fit_probe(Xn, y)
    preds = (_probe_margin(Xn, w, b) >= threshold).astype(int)
    accuracy = float((preds == y.astype(int)).mean())
    return {
        "w": w,
        "b": b,
        "threshold": threshold,
        "n_pos": n_pos,
        "n_neg": n_neg,
        "accuracy": accuracy,
        "dim": int(X.shape[1]),
    }


def _score_candidates(db, w, b, candidate_ids):
    """(ids, margins) for candidate_ids (or the whole corpus when None)."""
    import numpy as np

    if candidate_ids:
        mat, ids = _vectors_for_ids(db, list(candidate_ids))
    else:
        ids, mat = _all_corpus_vectors(db)
    if mat is None or len(ids) == 0:
        return [], np.empty(0, dtype=np.float64)
    margins = _probe_margin(_l2_normalize_rows(mat), w, b)
    return list(ids), margins


def train_probe(db, **kwargs: Any) -> dict[str, Any]:
    """Fit the numpy closed-form linear probe on keep/reject vectors.

    Degrade-first: if not trainable, return ``{"ok": False, "reason": ...}``
    merged with the full status snapshot — no model, no fabricated coefficients.
    When trainable, returns a JSON summary of the fit (counts, accuracy,
    threshold, dim); the raw 1152-d weights stay internal.
    """
    status = preference_status(db)
    if not status["trainable"]:
        return {"ok": False, "reason": status["reason"], **status}

    model = _train_probe_model(db)
    if model is None:
        return {"ok": False, "reason": REASON_VECTORS_UNAVAILABLE, **status}
    return {
        "ok": True,
        "n_pos": model["n_pos"],
        "n_neg": model["n_neg"],
        "accuracy": round(model["accuracy"], 4),
        "threshold": round(model["threshold"], 6),
        "dim": model["dim"],
    }


def centroid_preview(
    db,
    positive_ids: list[int],
    negative_ids: list[int] | None = None,
    threshold: float = 0.2,
) -> dict[str, Any]:
    """Nearest-centroid (NCM) preview — count-vs-threshold, NO writes.

    Degrade-first: if NOT every positive id has a vector, or the store lacks
    corpus-level coverage, return ``{"ok": False, "vectors_unavailable": True}``.
    Otherwise build the positive centroid (optionally contrasted against the
    negative centroid), score every corpus vector by cosine, and report how many
    clear ``threshold`` — a PREVIEW count for the operator before any
    ``tag_source='centroid'`` write (which stays a separate, backed-up step).
    """
    positive_ids = list(positive_ids or [])
    if not positive_ids:
        return {
            "ok": False,
            "vectors_unavailable": False,
            "reason": "no positive ids given",
            "positives_requested": 0,
            "positives_found": 0,
        }

    pos_mat, pos_found = _vectors_for_ids(db, positive_ids)
    corpus_covered = _has_corpus_coverage(db)
    if pos_mat is None or len(pos_found) < len(positive_ids) or not corpus_covered:
        return {
            "ok": False,
            "vectors_unavailable": True,
            "reason": REASON_VECTORS_UNAVAILABLE,
            "positives_requested": len(positive_ids),
            "positives_found": len(pos_found),
            "corpus_covered": corpus_covered,
            "threshold": threshold,
        }

    neg_mat = None
    negatives_used = 0
    if negative_ids:
        nmat, nfound = _vectors_for_ids(db, list(negative_ids))
        if nmat is not None and len(nfound):
            neg_mat = nmat
            negatives_used = len(nfound)

    centroid_vec = _centroid(pos_mat, neg_mat)
    ids, corpus = _all_corpus_vectors(db)
    if corpus is None or len(ids) == 0:
        return {
            "ok": False,
            "vectors_unavailable": True,
            "reason": REASON_VECTORS_UNAVAILABLE,
            "positives_requested": len(positive_ids),
            "positives_found": len(pos_found),
            "corpus_covered": corpus_covered,
            "threshold": threshold,
        }
    scores = _l2_normalize_rows(corpus) @ centroid_vec
    above = int((scores >= float(threshold)).sum())
    return {
        "ok": True,
        "above_threshold": above,
        "threshold": float(threshold),
        "scored": int(len(ids)),
        "positives_found": len(pos_found),
        "negatives_used": negatives_used,
    }


def preference_ranked_ids(
    db, candidate_ids: list[int] | None = None, limit: int = 200
) -> dict[str, Any]:
    """The ``sort=preference`` path — rank candidates by the trained probe.

    Degrade-first: returns ``{"ok": False, "reason": ..., "results": []}`` until
    the probe is trainable. Otherwise scores ``candidate_ids`` (or the whole
    corpus when None) and returns the top ``limit`` image ids best-first.
    """
    status = preference_status(db)
    if not status["trainable"]:
        return {"ok": False, "reason": status["reason"], "results": []}

    model = _train_probe_model(db)
    if model is None:
        return {"ok": False, "reason": REASON_VECTORS_UNAVAILABLE, "results": []}

    import numpy as np

    ids, margins = _score_candidates(db, model["w"], model["b"], candidate_ids)
    if not ids:
        return {"ok": True, "results": []}
    order = np.argsort(-margins)  # highest margin (most keep-like) first
    return {"ok": True, "results": [int(ids[i]) for i in order[:limit]]}


def edge_case_ids(
    db, candidate_ids: list[int] | None = None, limit: int = 200
) -> dict[str, Any]:
    """Uncertainty / margin sampling — the items the probe is LEAST sure about.

    The "ask me about edge cases" feed. Degrade-first with the SAME gate as the
    probe. When trainable, score ``candidate_ids`` (or the whole corpus when None)
    and return the ``limit`` items whose margin is nearest the decision threshold
    (max uncertainty) — binary margin sampling, the standard active-learning
    query strategy.
    """
    status = preference_status(db)
    if not status["trainable"]:
        return {"ok": False, "reason": status["reason"], "results": []}

    model = _train_probe_model(db)
    if model is None:
        return {"ok": False, "reason": REASON_VECTORS_UNAVAILABLE, "results": []}

    import numpy as np

    ids, margins = _score_candidates(db, model["w"], model["b"], candidate_ids)
    if not ids:
        return {"ok": True, "results": []}
    uncertainty = np.abs(margins - model["threshold"])
    order = np.argsort(uncertainty)  # nearest the boundary first = most uncertain
    return {"ok": True, "results": [int(ids[i]) for i in order[:limit]]}
