#!/usr/bin/env python3
"""
SigLIP 2 re-embed — replace-in-place, safe-swap (Wave-1 step 2).

Re-embeds the whole corpus from ``google/siglip-so400m-patch14-384`` to
``google/siglip2-so400m-patch14-384`` (Apache-2.0). SigLIP 2 SO400M is the SAME
shape — **1152-dim → zero schema change**. The ``vec_siglip_1152`` table and the
TurboVec ``.idx`` format are unchanged; only the model that produces the vectors
moves. The query (text) tower MUST move in lockstep — a mismatched image/text
pair silently poisons text→image (``knowledge/vendors/siglip-quirks.md``).

THIS SCRIPT IS A PLAYBOOK JOB. It is meant to run LATER on a rented GPU, not as a
build step. It is **dry-run by default**; ``--apply`` is required to mutate
anything, and ``--apply`` additionally refuses unless ``--ack-text-tower`` is
passed (forcing the operator to confirm the text tower was upgraded too).

Safe-swap protocol (``--apply``), abort on any failure (live store untouched):
  1. backup_db.sh (WAL-safe; refuse to proceed if it fails)
  2. embed every image into a TEMP TurboVec ``.idx`` (``…idx.new``) + TEMP vec
     table (``vec_siglip_1152_new``) via the compute seam batch path
  3. self-retrieval parity gate on the TEMP store (top-1 == self, cosine > thr)
  4. atomic swap: rename temp vec table over the live one (one txn) +
     ``os.replace`` the ``.idx`` over the live index
  5. drop temp artifacts
  6. remind: recompute derived centroid exemplars (not stored — no migration)

Pure functions (plan builder, swap-SQL builder, gate decision) carry the logic
and are unit-tested without torch / a model / the network. torch + transformers +
the seam backend are only touched inside the ``--apply`` embed step.

Usage
-----
    # dry-run plan (DEFAULT — touches nothing):
    python3 scripts/reembed_siglip2.py --db data/catalog.db

    # mutate (rented-GPU session only):
    python3 scripts/reembed_siglip2.py --db data/catalog.db \
        --apply --ack-text-tower --threshold 0.99
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline.tier1_embedder import (  # noqa: E402
    DEFAULT_INDEX_PATH,
    VEC_TABLE,
)

OLD_MODEL_ID = "google/siglip-so400m-patch14-384"
NEW_MODEL_ID = "google/siglip2-so400m-patch14-384"
EMBEDDING_DIM = 1152  # SO400M shape is unchanged between SigLIP 1 and 2.

DEFAULT_DB = REPO_ROOT / "data" / "catalog.db"
DEFAULT_IDS_FILE = REPO_ROOT / "data" / "validation" / "tier1_ids.json"
DEFAULT_THRESHOLD = 0.99

# Temp artifact names (sit beside / inside the live store; dropped after swap).
TEMP_VEC_TABLE = f"{VEC_TABLE}_new"
TEMP_INDEX_SUFFIX = ".new"


# --------------------------------------------------------------------------- #
# Pure helpers — exercised by tests WITHOUT torch / a model / the network.     #
# --------------------------------------------------------------------------- #
def temp_index_path(index_path: str | Path) -> Path:
    """The temp ``.idx`` path the embed step writes (live path + ``.new``)."""
    p = Path(index_path)
    return p.with_name(p.name + TEMP_INDEX_SUFFIX)


def build_swap_sql(
    live_table: str = VEC_TABLE, temp_table: str = TEMP_VEC_TABLE
) -> str:
    """SQL that atomically replaces the live vec table with the temp one. PURE.

    Run inside ONE transaction: drop the old table, rename the freshly-built
    temp table into its place. sqlite executes these as a unit when wrapped in
    BEGIN/COMMIT by the caller.
    """
    return f"DROP TABLE {live_table};\nALTER TABLE {temp_table} RENAME TO {live_table};"


def gate_passed(probe_results: list[dict[str, Any]]) -> bool:
    """Whether every probe self-retrieved. PURE.

    ``probe_results`` rows carry a boolean ``"pass"`` (set by the embed step from
    ``verify_self_retrieval.evaluate_probe``). An empty set never passes — a gate
    that checked zero probes must not authorize throwing away the old store.
    """
    return len(probe_results) > 0 and all(bool(r.get("pass")) for r in probe_results)


def build_plan(
    db_path: str | Path,
    index_path: str | Path,
    corpus_size: int,
    probe_ids: list[int],
    threshold: float,
    apply: bool,
    ack_text_tower: bool,
) -> dict[str, Any]:
    """Assemble the dry-run plan / the apply preflight summary. PURE.

    Describes the model transition, the temp artifacts, the gate, and the exact
    mutation steps the ``--apply`` path WOULD run. No side effects.
    """
    idx = Path(index_path)
    return {
        "job": "siglip2-reembed-safe-swap",
        "model_transition": {"from": OLD_MODEL_ID, "to": NEW_MODEL_ID},
        "embedding_dim": EMBEDDING_DIM,
        "schema_change": False,
        "db_path": str(db_path),
        "corpus_size": corpus_size,
        "live_index": str(idx),
        "temp_index": str(temp_index_path(idx)),
        "live_vec_table": VEC_TABLE,
        "temp_vec_table": TEMP_VEC_TABLE,
        "probe_ids": probe_ids,
        "threshold": threshold,
        "apply": apply,
        "ack_text_tower": ack_text_tower,
        "text_tower_lockstep": (
            f"set pipeline/text_embedder.py MODEL_ID = {NEW_MODEL_ID!r} "
            "BEFORE serving search (image+text towers MUST match)."
        ),
        "steps": [
            "1. backup_db.sh (WAL-safe; abort if it fails)",
            f"2. embed {corpus_size} images -> TEMP {temp_index_path(idx).name} "
            f"+ TEMP table {TEMP_VEC_TABLE} via the compute seam batch path",
            f"3. self-retrieval parity gate (top-1==self, cosine>{threshold})",
            "4. atomic swap: rename temp vec table over live (1 txn) + "
            "os.replace .idx over live",
            "5. drop temp artifacts",
            "6. recompute derived centroid exemplars (no migration; derived)",
        ],
    }


# --------------------------------------------------------------------------- #
# I/O helpers.                                                                 #
# --------------------------------------------------------------------------- #
def load_probe_ids(ids_arg: str | None) -> list[int]:
    """Resolve the probe id set from --ids (a JSON file path or inline JSON list).

    Defaults to ``data/validation/tier1_ids.json`` (the e2e baseline ids).
    Returns ``[]`` if the default file is absent (so the dry-run plan still
    builds on a fresh checkout).
    """
    if ids_arg is None:
        if not DEFAULT_IDS_FILE.exists():
            return []
        raw = DEFAULT_IDS_FILE.read_text()
    else:
        candidate = Path(ids_arg)
        raw = candidate.read_text() if candidate.exists() else ids_arg
    return [int(i) for i in json.loads(raw)]


def corpus_size(db_path: str | Path) -> int:
    """Total ``images`` row count (the embed denominator). 0 if the db is absent."""
    if not Path(db_path).exists():
        return 0
    from sqlalchemy import func

    from pipeline.database import Database, Image

    db = Database(str(db_path))
    with db.get_session() as session:
        return int(session.query(func.count(Image.id)).scalar() or 0)


def run_backup(db_path: str | Path) -> None:
    """WAL-safe backup via scripts/backup_db.sh. Raises if it exits non-zero."""
    script = REPO_ROOT / "scripts" / "backup_db.sh"
    subprocess.run(["bash", str(script), str(db_path)], check=True, cwd=str(REPO_ROOT))


# --------------------------------------------------------------------------- #
# The --apply path — heavy + mutating. Imported deps stay inside this branch.  #
# --------------------------------------------------------------------------- #
def _embed_to_temp(
    db_path: str | Path,
    temp_index: Path,
    threshold: float,
    probe_ids: list[int],
) -> dict[str, Any]:  # pragma: no cover - runs only on a rented GPU
    """Embed the corpus to the TEMP index + temp vec table, then run the gate.

    Uses the SigLIP 2 model id through the same Tier1Embedder machinery (the
    compute seam's ``embed`` resolves to this on the local backend; the rented
    backend produces identical 1152-dim vectors over HTTP). Writes ONLY temp
    artifacts — the live store is never touched here. Returns the gate report.

    NOT executed in tests (no GPU, no weights); guarded ``pragma: no cover``.
    """
    from pipeline.database import Database, Image
    from pipeline.tier1_embedder import (
        Tier1Embedder,
        TurboVecStore,
        open_vec_db,
        serialize_float32,
    )
    from scripts.verify_self_retrieval import evaluate_probe

    # A Tier1Embedder pinned to the SigLIP 2 checkpoint, writing the temp index.
    embedder = Tier1Embedder(index_path=temp_index)
    embedder.MODEL_ID = NEW_MODEL_ID  # the only model-id swap the embed needs.
    store = TurboVecStore(dim=EMBEDDING_DIM, bit_width=4, path=temp_index)

    conn = open_vec_db(str(db_path))
    # Build the temp float-rescore table under the TEMP name (same shape as the
    # live VEC_TABLE). The live table is never touched here.
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {TEMP_VEC_TABLE} USING vec0("
        f"image_id INTEGER PRIMARY KEY, "
        f"embedding float[{EMBEDDING_DIM}] distance_metric=cosine)"
    )
    conn.commit()

    db = Database(str(db_path))
    with db.get_session() as session:
        rows = session.query(Image.id, Image.path).order_by(Image.id).all()
    for image_id, rel_path in rows:
        vec = embedder.embed_image(rel_path)
        store.add(int(image_id), vec)
        blob = serialize_float32(vec)
        conn.execute(
            f"DELETE FROM {TEMP_VEC_TABLE} WHERE image_id = ?", (int(image_id),)
        )
        conn.execute(
            f"INSERT INTO {TEMP_VEC_TABLE} (image_id, embedding) VALUES (?, ?)",
            (int(image_id), blob),
        )
    conn.commit()
    store.save()  # persist the temp .idx for the swap step.

    # Parity gate against the TEMP table (exact float cosine rescore).
    results: list[dict[str, Any]] = []
    for pid in probe_ids:
        row = next((r for r in rows if int(r[0]) == int(pid)), None)
        if row is None:
            results.append({"id": pid, "pass": False, "reason": "no image row"})
            continue
        ranked = conn.execute(
            f"SELECT image_id, distance FROM {TEMP_VEC_TABLE} "
            f"WHERE embedding MATCH ? ORDER BY distance LIMIT 1",
            (serialize_float32(embedder.embed_image(row[1])),),
        ).fetchall()
        neighbor_id = int(ranked[0][0]) if ranked else None
        cosine = 1.0 - float(ranked[0][1]) if ranked else 0.0
        results.append(
            {
                "id": int(pid),
                "neighbor": neighbor_id,
                "cosine": cosine,
                "pass": evaluate_probe(int(pid), neighbor_id, cosine, threshold),
            }
        )
    conn.close()
    return {"checked": len(results), "results": results}


def _swap_into_place(
    db_path: str | Path, temp_index: Path, live_index: Path
) -> None:  # pragma: no cover - runs only on a rented GPU
    """Atomically replace the live vec table + index with the temp ones."""
    from pipeline.tier1_embedder import open_vec_db

    conn = open_vec_db(str(db_path))
    try:
        conn.execute("BEGIN")
        for stmt in build_swap_sql().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()
    os.replace(str(temp_index), str(live_index))


def apply_reembed(
    db_path: str | Path,
    index_path: str | Path,
    threshold: float,
    probe_ids: list[int],
) -> int:  # pragma: no cover - runs only on a rented GPU
    """Run the full safe-swap. Returns 0 on success, non-zero on a gated abort."""
    live_index = Path(index_path)
    temp_index = temp_index_path(live_index)

    run_backup(db_path)  # step 1 — abort (raises) if backup fails.
    gate = _embed_to_temp(db_path, temp_index, threshold, probe_ids)  # steps 2-3
    if not gate_passed(gate["results"]):
        print(
            "PARITY GATE FAILED — live store untouched; temp artifacts kept "
            f"for inspection. report={json.dumps(gate)}",
            file=sys.stderr,
        )
        return 1
    _swap_into_place(db_path, temp_index, live_index)  # step 4
    print(
        "SWAP OK — SigLIP 2 vectors are live. REMEMBER: recompute derived "
        "centroid exemplars (they are not stored vectors)."
    )
    return 0


# --------------------------------------------------------------------------- #
# CLI.                                                                          #
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "SigLIP 2 re-embed (replace-in-place, safe-swap). DRY-RUN by default; "
            "--apply mutates and requires --ack-text-tower. Meant to run on a "
            "rented GPU, NOT as a build step."
        )
    )
    ap.add_argument(
        "--db", default=str(DEFAULT_DB), help=f"catalog.db (default {DEFAULT_DB})"
    )
    ap.add_argument(
        "--index", default=str(DEFAULT_INDEX_PATH), help="live TurboVec .idx path"
    )
    ap.add_argument("--ids", default=None, help="probe ids (JSON list or file path)")
    ap.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"min self-cosine for the parity gate (default {DEFAULT_THRESHOLD})",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="MUTATE: run the safe-swap (default is a dry-run plan).",
    )
    ap.add_argument(
        "--ack-text-tower",
        action="store_true",
        help="confirm pipeline/text_embedder.py MODEL_ID was upgraded in lockstep "
        "(REQUIRED with --apply; image+text towers must match).",
    )
    ap.add_argument("--out", default=None, help="write the plan/report JSON here")
    args = ap.parse_args(argv)

    probe_ids = load_probe_ids(args.ids)
    plan = build_plan(
        db_path=args.db,
        index_path=args.index,
        corpus_size=corpus_size(args.db),
        probe_ids=probe_ids,
        threshold=args.threshold,
        apply=args.apply,
        ack_text_tower=args.ack_text_tower,
    )

    if not args.apply:
        _emit(plan, args.out)
        print("DRY-RUN — nothing mutated. Re-run with --apply --ack-text-tower.")
        return 0

    if not args.ack_text_tower:
        _emit(plan, args.out)
        print(
            "REFUSING --apply without --ack-text-tower: upgrade "
            f"pipeline/text_embedder.py MODEL_ID to {NEW_MODEL_ID!r} first "
            "(image+text towers MUST match — text2image poison trap).",
            file=sys.stderr,
        )
        return 2

    _emit(plan, args.out)
    return apply_reembed(args.db, args.index, args.threshold, probe_ids)


def _emit(report: dict[str, Any], out: str | None) -> None:
    text = json.dumps(report, indent=2)
    if out:
        Path(out).write_text(text)
    print(text)


if __name__ == "__main__":
    sys.exit(main())
