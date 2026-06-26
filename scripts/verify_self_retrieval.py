#!/usr/bin/env python3
"""
ADR-0005 GATE 0 — embedding-space self-retrieval verifier (runs on the Mac).

For a fixed set of known image ids, re-embed each image LOCALLY on MPS via
``Tier1Embedder.embed_image`` (same ``get_image_features().pooler_output``,
L2-normalized) and confirm its top cosine neighbor in ``vec_siglip_1152`` is
ITSELF at cosine > 0.99 (the ADR-0005 threshold — looser than parity's 0.9999
because this is recompute-vs-stored across two runtimes: local MPS vs the H100).

What this gate proves and does NOT prove
----------------------------------------
PASS means ``vec_siglip_1152`` is a coherent, self-consistent metric space and
the checkpoint is deterministic / non-degenerate. It is the prerequisite for
find-similar (image -> image) AND a precondition for text2image.

It does NOT prove cross-modal validity — a *vision-only* checkpoint passes this
gate trivially. The text-tower / cross-modal proof is ADR-0006 GATE 1.

Authorization
-------------
A PASS here authorizes the OPERATOR to set ``TEXT2IMAGE_GATE_PASSED=1`` (jointly
with ADR-0006 GATE 1) and to ship find-similar (GATE 0 alone). This script does
NOT flip any env var — it only reports. The operator flips the flag by hand.

Today (2026-06-23) ``vec_siglip_1152`` holds only the ~65-vector validation
baseline, not the 26,590-image corpus. So this script reports ``insufficient``
and exits 2 — that is the EXPECTED path until the H100 full embed run lands.

Exit codes
----------
    0  all probes pass (top-1 == self AND cosine > threshold)
    1  vectors sufficient but at least one probe FAILED (poisoned / wrong checkpoint)
    2  insufficient vectors — the full embed run has not landed; gate cannot run

Usage
-----
    python3 scripts/verify_self_retrieval.py \
        --ids data/validation/tier1_ids.json \
        --threshold 0.99 \
        --db data/catalog.db \
        --out outputs/self_retrieval.json

Heavy deps (torch / transformers) are imported lazily ONLY in the "ready" branch,
so the readiness pre-check and ``--help`` run without them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_IDS_FILE = REPO_ROOT / "data" / "validation" / "tier1_ids.json"
DEFAULT_DB = REPO_ROOT / "data" / "catalog.db"
DEFAULT_THRESHOLD = 0.99

# Below this fraction of the image corpus, treat the vec store as not-yet-landed
# (the full embed run has not populated vec_siglip_1152). 90% leaves slack for a
# handful of unembeddable / corrupt images without falsely declaring readiness.
COVERAGE_FRACTION = 0.90


# --------------------------------------------------------------------------- #
# Pure decision logic — exercised by tests WITHOUT torch or real vectors.      #
# --------------------------------------------------------------------------- #
def classify_readiness(
    vectors_present: int,
    corpus_size: int,
    probe_ids_present: int,
    probe_ids_total: int,
) -> str:
    """Decide whether GATE 0 can run. Returns "insufficient" | "ready".

    PURE. "ready" requires BOTH:
      * the vec store covers ~the whole corpus (>= COVERAGE_FRACTION of it), AND
      * every probe id has a stored vector to retrieve against.
    Either gap -> "insufficient" (the expected state until the H100 run lands).
    A corpus_size <= 0 is treated as unknown -> insufficient (never divide-by-zero).
    An EMPTY probe set (probe_ids_total <= 0) is "insufficient": a gate that checks
    zero probes must never report "ready" (it would authorize text2image on zero
    verification once the corpus is fully embedded).
    """
    if corpus_size <= 0:
        return "insufficient"
    if probe_ids_total <= 0:
        return "insufficient"
    if probe_ids_present < probe_ids_total:
        return "insufficient"
    if vectors_present < int(COVERAGE_FRACTION * corpus_size):
        return "insufficient"
    return "ready"


def evaluate_probe(
    probe_id: int,
    neighbor_id: int | None,
    cosine: float,
    threshold: float = DEFAULT_THRESHOLD,
) -> bool:
    """A single probe PASSES iff its top neighbor is itself AND cosine > threshold.

    PURE. ``neighbor_id`` is the id of the top-1 rescore neighbor (None when the
    rescore returned nothing). A wrong neighbor OR a cosine at/below ``threshold``
    fails the probe — both are how a poisoned / wrong-checkpoint store is caught.
    """
    if neighbor_id is None:
        return False
    return neighbor_id == probe_id and cosine > threshold


# --------------------------------------------------------------------------- #
# I/O helpers.                                                                 #
# --------------------------------------------------------------------------- #
def load_probe_ids(ids_arg: str | None) -> list[int]:
    """Resolve the probe id set from --ids (a JSON file path or inline JSON list).

    Defaults to ``data/validation/tier1_ids.json`` (the 10 e2e baseline ids).
    """
    if ids_arg is None:
        raw = DEFAULT_IDS_FILE.read_text()
    else:
        candidate = Path(ids_arg)
        raw = candidate.read_text() if candidate.exists() else ids_arg
    parsed = json.loads(raw)
    return [int(i) for i in parsed]


def count_present_probe_ids(db_path: str | Path, probe_ids: list[int]) -> int:
    """How many of ``probe_ids`` already have a vector in vec_siglip_1152.

    Reuses the same vec store the search path reads. Returns 0 on any error
    (missing table / extension) so the readiness pre-check never raises.
    """
    from pipeline.tier1_embedder import VEC_TABLE, open_vec_db

    conn = None
    present = 0
    try:
        conn = open_vec_db(str(db_path))
        for image_id in probe_ids:
            row = conn.execute(
                f"SELECT 1 FROM {VEC_TABLE} WHERE image_id = ?", (int(image_id),)
            ).fetchone()
            if row is not None:
                present += 1
    except Exception:
        return 0
    finally:
        if conn is not None:
            conn.close()
    return present


def corpus_size(db_path: str | Path) -> int:
    """Total ``images`` row count (the coverage denominator)."""
    from pipeline.database import Database, Image

    db = Database(str(db_path))
    with db.get_session() as session:
        from sqlalchemy import func

        return int(session.query(func.count(Image.id)).scalar() or 0)


# --------------------------------------------------------------------------- #
# The "ready" branch — re-embed locally + rescore (lazy torch/transformers).   #
# --------------------------------------------------------------------------- #
def _resolve_rel_path(db_path: str | Path, image_id: int) -> str | None:
    """DB-relative path for an image id (Tier1Embedder.embed_image resolves it)."""
    from pipeline.database import Database, Image

    db = Database(str(db_path))
    with db.get_session() as session:
        row = session.query(Image.path).filter(Image.id == int(image_id)).first()
    return str(row[0]) if row else None


def run_gate(
    db_path: str | Path, probe_ids: list[int], threshold: float
) -> dict[str, Any]:
    """Re-embed each probe locally, rescore against vec_siglip_1152, evaluate.

    Heavy deps (torch via Tier1Embedder, sqlite-vec via open_vec_db) are imported
    here, only after readiness is confirmed. Mirrors validate_h100_parity.py's
    report shape (checked / mismatches / pass / worst_cosine / detail).
    """
    from pipeline.tier1_embedder import (
        Tier1Embedder,
        open_vec_db,
        serialize_float32,
    )
    from webui.search import _vec_rescore

    embedder = Tier1Embedder()
    conn = open_vec_db(str(db_path))
    worst_cosine = 1.0
    failures: list[dict[str, Any]] = []
    checked = 0
    try:
        for probe_id in probe_ids:
            rel_path = _resolve_rel_path(db_path, probe_id)
            if rel_path is None:
                failures.append({"id": probe_id, "reason": "no image row"})
                continue
            local_vec = embedder.embed_image(rel_path)
            blob = serialize_float32(local_vec)
            # Top-1 neighbor over the WHOLE store (no allowlist), same SQL the
            # search path uses for the exact cosine rescore.
            ranked = _vec_rescore(conn, blob, allowlist=None, k=1)
            checked += 1
            neighbor_id = ranked[0][0] if ranked else None
            cosine = ranked[0][1] if ranked else 0.0
            worst_cosine = min(worst_cosine, cosine)
            if not evaluate_probe(probe_id, neighbor_id, cosine, threshold):
                failures.append(
                    {
                        "id": probe_id,
                        "wrong_neighbor": neighbor_id
                        if neighbor_id != probe_id
                        else None,
                        "cosine": cosine,
                    }
                )
    finally:
        conn.close()

    return {
        "status": "ready",
        "checked": checked,
        "mismatches": len(failures),
        # A PASS requires real work: zero probes checked is never a pass.
        "pass": checked > 0 and len(failures) == 0,
        "threshold": threshold,
        "worst_cosine": worst_cosine,
        "detail": failures[:20],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "ADR-0005 GATE 0 self-retrieval verifier. A PASS authorizes the "
            "operator to flip TEXT2IMAGE_GATE_PASSED=1 (with ADR-0006 GATE 1) "
            "and to ship find-similar; this script does NOT flip it."
        )
    )
    ap.add_argument(
        "--ids",
        default=None,
        help="JSON list of probe ids, or a path to a JSON file "
        f"(default: {DEFAULT_IDS_FILE})",
    )
    ap.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"min self-cosine for a probe to pass (default {DEFAULT_THRESHOLD})",
    )
    ap.add_argument(
        "--db", default=str(DEFAULT_DB), help=f"catalog.db path (default {DEFAULT_DB})"
    )
    ap.add_argument("--out", default=None, help="Write the JSON report here")
    args = ap.parse_args(argv)

    probe_ids = load_probe_ids(args.ids)
    probe_total = len(probe_ids)

    # --- Pre-check: is the vec store ready to run the gate at all? ---
    from pipeline.database import Database
    from webui.search import vector_count

    db = Database(args.db)
    vectors_present = vector_count(db)
    n_corpus = corpus_size(args.db)
    probe_present = count_present_probe_ids(args.db, probe_ids)

    readiness = classify_readiness(
        vectors_present, n_corpus, probe_present, probe_total
    )

    if readiness == "insufficient":
        report = {
            "status": "insufficient",
            "vectors_present": vectors_present,
            "corpus_size": n_corpus,
            "probe_ids_present": probe_present,
            "probe_ids_total": probe_total,
        }
        _emit(report, args.out)
        print(
            "insufficient vectors — the full embed run has not landed; "
            f"gate cannot run ({vectors_present} vectors, {probe_present}/"
            f"{probe_total} probe ids present).",
            file=sys.stderr,
        )
        return 2

    # --- Ready: re-embed + rescore (heavy deps imported inside run_gate). ---
    report = run_gate(args.db, probe_ids, args.threshold)
    _emit(report, args.out)
    if report["pass"]:
        print(
            "GATE 0 PASS — self-retrieval coherent. Operator MAY set "
            "TEXT2IMAGE_GATE_PASSED=1 (only with ADR-0006 GATE 1) and ship "
            "find-similar. This script did NOT flip it."
        )
        return 0
    print(
        f"GATE 0 FAIL — {report['mismatches']} probe(s) failed; "
        f"worst_cosine={report['worst_cosine']:.4f}. Vectors may be poisoned "
        "(wrong checkpoint); re-run the H100 embed.",
        file=sys.stderr,
    )
    return 1


def _emit(report: dict[str, Any], out: str | None) -> None:
    text = json.dumps(report, indent=2)
    if out:
        Path(out).write_text(text)
    print(text)


if __name__ == "__main__":
    sys.exit(main())
