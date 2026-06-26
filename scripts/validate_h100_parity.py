#!/usr/bin/env python3
"""
H100 OFFLOAD — parity validator (runs on the Mac).

Compares the artifacts the H100 produced against locally-computed reference
output for the SAME image ids, and emits a JSON pass/fail report. This is the
gate the research brief requires before trusting the full 26.5k run: run a small
pilot (e.g. 500 images) on the box, recompute those same images locally, and
diff.

What "parity" means per tier (the bar from research brief 06):
  Tier 0 (tags):     same (category, value, tag_source) tuples, confidence
                     within ABS_CONF_TOL (default 1e-4).
  Tier 1 (embed):    per-id L2-norm-diff < VEC_L2_TOL (default 1e-4) AND
                     cosine > VEC_COS_TOL (default 0.9999).
  Tier 2 (captions): deterministic exact string match (vLLM temp=0, seed=0).
  Tier 3 (nudenet):  same label set; each matched bbox within BBOX_PX_TOL px
                     (default 2) on all four coords.

Local reference is computed with the SAME tier modules the pipeline uses
(pipeline/tier{0,1,3}_*.py), so "local" here is ground truth. For Tier 2 the
local Qwen captioner is a DIFFERENT model than JoyCaption, so Tier-2 parity is
NOT model-vs-model; it is **remote-vs-remote determinism**: pass a second remote
captions file (--remote-captions-b) from a repeat run and require an exact match.
If only one captions file is given, Tier 2 reports "skipped" (can't prove
determinism from a single sample).

Usage (pilot parity check):
  # 1) recompute the pilot ids locally into a reference dir
  python3 scripts/validate_h100_parity.py \
      --artifacts outputs/h100/<stamp>/artifacts \
      --manifest  outputs/h100/<stamp>/manifest.json \
      --staging   outputs/h100/<stamp>/staging \
      --tiers 0,1,3 \
      --out outputs/h100/<stamp>/parity.json

  # Tier-2 determinism (two remote runs):
  python3 scripts/validate_h100_parity.py --tiers 2 \
      --artifacts runA --remote-captions-b runB/captions.jsonl ...

The validator recomputes Tier 0/1/3 locally from the SAME <id>.webp files in
--staging (the exact bytes that were uploaded), so preprocessing is identical to
what the box saw. Requires the local weights to be present (models/ + torch for
Tier 1).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

ABS_CONF_TOL = 1e-4
VEC_L2_TOL = 1e-4
VEC_COS_TOL = 0.9999
BBOX_PX_TOL = 2


def iter_jsonl(path: Path) -> dict[int, Any]:
    """Load a {id:...} JSONL into {id: obj}."""
    out: dict[int, Any] = {}
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                obj = json.loads(line)
                out[int(obj["id"])] = obj
    return out


# ---------------------------------------------------------------------------
# Tier 0 parity — recompute tags locally from <id>.webp, compare tuples.
# ---------------------------------------------------------------------------
def _local_tier0_rows(webp: Path) -> list[dict[str, Any]]:
    from PIL import Image

    from pipeline.tier0_tagger import (
        Tier0Tagger,
    )

    tagger = Tier0Tagger()
    with Image.open(webp) as img:
        img = img.convert("RGB")
        wd = tagger._run_wd(img)  # noqa: SLF001 - intentional reuse of exact path
        joy = tagger._run_joytag(img)  # noqa: SLF001
    rows: list[dict[str, Any]] = []
    for category, value, score in wd:
        rows.append(
            {
                "category": category,
                "value": value,
                "confidence": score,
                "tag_source": "wd_eva02",
            }
        )
    for value, score in joy:
        rows.append(
            {
                "category": "tags",
                "value": value,
                "confidence": score,
                "tag_source": "joytag",
            }
        )
    return rows


def _rows_to_map(rows: list[dict[str, Any]]) -> dict[tuple, float]:
    return {
        (r["category"], r["value"], r["tag_source"]): float(r["confidence"])
        for r in rows
    }


def validate_tier0(artifacts: Path, staging: Path, ids: list[int]) -> dict[str, Any]:
    remote = iter_jsonl(artifacts / "tags.jsonl")
    mismatches: list[dict[str, Any]] = []
    checked = 0
    for img_id in ids:
        webp = staging / f"{img_id}.webp"
        if img_id not in remote or not webp.exists():
            mismatches.append(
                {"id": img_id, "reason": "missing remote or staging file"}
            )
            continue
        local_map = _rows_to_map(_local_tier0_rows(webp))
        remote_map = _rows_to_map(remote[img_id].get("rows", []))
        checked += 1
        only_local = set(local_map) - set(remote_map)
        only_remote = set(remote_map) - set(local_map)
        conf_off = [
            {"tuple": list(k), "local": local_map[k], "remote": remote_map[k]}
            for k in (set(local_map) & set(remote_map))
            if abs(local_map[k] - remote_map[k]) > ABS_CONF_TOL
        ]
        if only_local or only_remote or conf_off:
            mismatches.append(
                {
                    "id": img_id,
                    "only_local": [list(k) for k in only_local],
                    "only_remote": [list(k) for k in only_remote],
                    "conf_off": conf_off,
                }
            )
    return {
        "tier": 0,
        "checked": checked,
        "mismatches": len(mismatches),
        "pass": len(mismatches) == 0,
        "abs_conf_tol": ABS_CONF_TOL,
        "detail": mismatches[:20],
    }


# ---------------------------------------------------------------------------
# Tier 1 parity — recompute embeddings locally, compare L2-norm-diff + cosine.
# ---------------------------------------------------------------------------
def validate_tier1(artifacts: Path, staging: Path, ids: list[int]) -> dict[str, Any]:
    emb_path = artifacts / "embeddings.npy"
    ids_path = artifacts / "ids.npy"
    if not emb_path.exists() or not ids_path.exists():
        return {
            "tier": 1,
            "pass": False,
            "reason": "remote embeddings.npy/ids.npy missing",
        }

    from pipeline.tier1_embedder import Tier1Embedder, l2_normalize

    remote_mat = np.load(emb_path).astype(np.float32)
    remote_ids = [int(i) for i in np.load(ids_path).astype(np.int64)]
    remote_lookup = {i: remote_mat[k] for k, i in enumerate(remote_ids)}

    embedder = Tier1Embedder()
    worst_l2 = 0.0
    worst_cos = 1.0
    mismatches: list[dict[str, Any]] = []
    checked = 0
    for img_id in ids:
        webp = staging / f"{img_id}.webp"
        if img_id not in remote_lookup or not webp.exists():
            mismatches.append(
                {"id": img_id, "reason": "missing remote vec or staging file"}
            )
            continue
        # Local embed reads the absolute path directly (bypass content-root resolve).
        local = embedder.embed_image(str(webp.resolve()))
        rem = l2_normalize(remote_lookup[img_id])
        l2 = float(np.linalg.norm(local - rem))
        cos = float(np.dot(local, rem))  # both unit-norm -> cosine
        worst_l2 = max(worst_l2, l2)
        worst_cos = min(worst_cos, cos)
        checked += 1
        if l2 >= VEC_L2_TOL or cos <= VEC_COS_TOL:
            mismatches.append({"id": img_id, "l2_diff": l2, "cosine": cos})
    return {
        "tier": 1,
        "checked": checked,
        "mismatches": len(mismatches),
        "pass": len(mismatches) == 0,
        "worst_l2_diff": worst_l2,
        "worst_cosine": worst_cos,
        "l2_tol": VEC_L2_TOL,
        "cos_tol": VEC_COS_TOL,
        "detail": mismatches[:20],
    }


# ---------------------------------------------------------------------------
# Tier 2 parity — remote-vs-remote determinism (exact caption match).
# ---------------------------------------------------------------------------
def validate_tier2(
    artifacts: Path, remote_b: Path | None, ids: list[int]
) -> dict[str, Any]:
    a = iter_jsonl(artifacts / "captions.jsonl")
    if remote_b is None:
        return {
            "tier": 2,
            "pass": None,
            "skipped": True,
            "reason": "Tier-2 parity requires --remote-captions-b (a second deterministic run); "
            "local Qwen != JoyCaption so model-vs-model is N/A.",
        }
    b = iter_jsonl(remote_b)
    mismatches: list[dict[str, Any]] = []
    checked = 0
    for img_id in ids:
        if img_id not in a or img_id not in b:
            mismatches.append({"id": img_id, "reason": "caption missing in one run"})
            continue
        checked += 1
        if a[img_id]["caption"].strip() != b[img_id]["caption"].strip():
            mismatches.append(
                {
                    "id": img_id,
                    "a": a[img_id]["caption"][:120],
                    "b": b[img_id]["caption"][:120],
                }
            )
    return {
        "tier": 2,
        "checked": checked,
        "mismatches": len(mismatches),
        "pass": len(mismatches) == 0,
        "mode": "remote-vs-remote-determinism",
        "detail": mismatches[:20],
    }


# ---------------------------------------------------------------------------
# Tier 3 parity — recompute nudenet locally, compare labels + bbox px.
# ---------------------------------------------------------------------------
def _match_regions(local: list[dict], remote: list[dict]) -> list[dict[str, Any]]:
    """Greedy label-matched bbox diff. Returns per-region px deltas / mismatches."""
    issues: list[dict[str, Any]] = []
    remaining = list(remote)
    for lr in local:
        # find a same-label remote region with the closest box
        cand = [
            (idx, rr) for idx, rr in enumerate(remaining) if rr["label"] == lr["label"]
        ]
        if not cand:
            issues.append({"local_label": lr["label"], "reason": "no remote match"})
            continue
        best_idx, best = min(
            cand,
            key=lambda t: max(abs(a - b) for a, b in zip(lr["box"], t[1]["box"])),
        )
        max_px = max(abs(a - b) for a, b in zip(lr["box"], best["box"]))
        if max_px > BBOX_PX_TOL:
            issues.append(
                {
                    "label": lr["label"],
                    "max_px": max_px,
                    "local": lr["box"],
                    "remote": best["box"],
                }
            )
        remaining.pop(best_idx)
    for rr in remaining:
        issues.append(
            {"remote_label": rr["label"], "reason": "unmatched remote region"}
        )
    return issues


def validate_tier3(artifacts: Path, staging: Path, ids: list[int]) -> dict[str, Any]:
    remote = iter_jsonl(artifacts / "nudenet.jsonl")
    from pipeline.tier3_nudenet import Tier3NudeNet

    tier3 = Tier3NudeNet()
    mismatches: list[dict[str, Any]] = []
    checked = 0
    for img_id in ids:
        webp = staging / f"{img_id}.webp"
        if img_id not in remote or not webp.exists():
            mismatches.append(
                {"id": img_id, "reason": "missing remote or staging file"}
            )
            continue
        local_regions = tier3.detect_image(str(webp.resolve()))
        issues = _match_regions(local_regions, remote[img_id].get("regions", []))
        checked += 1
        if issues:
            mismatches.append({"id": img_id, "issues": issues})
    return {
        "tier": 3,
        "checked": checked,
        "mismatches": len(mismatches),
        "pass": len(mismatches) == 0,
        "bbox_px_tol": BBOX_PX_TOL,
        "detail": mismatches[:20],
    }


def parse_tiers(raw: str) -> set[int]:
    return {int(t.strip()) for t in raw.split(",") if t.strip() != ""}


# ---------------------------------------------------------------------------
# Store row-parity gate (find-similar go-live, Phase 0).
# ---------------------------------------------------------------------------
def validate_store_parity(db_path: str | Path) -> dict[str, Any]:
    """Assert the three Tier-1 stores agree on row count and are non-empty.

    The find-similar go-live spec (Phase 0) requires the float rescore table,
    the turbovec ANN index, and the set of imported image ids to be in lockstep
    before search is trusted. Reads only — never writes.

    Counts:
      * ``vec_siglip_1152`` rows (the sqlite-vec float rescore table);
      * the turbovec ``.idx`` row count (``len(TurboVecStore.load(...))``);
      * imported image ids that have a vector (the float table's distinct ids).

    All three must be equal AND non-zero. Returns a report dict; ``pass`` is True
    only when parity holds.
    """
    from pipeline.tier1_embedder import DEFAULT_INDEX_PATH, VEC_TABLE, open_vec_db

    db_path = Path(db_path)

    # vec_siglip_1152 is a vec0 virtual table — open via open_vec_db so the
    # sqlite-vec extension is loaded (a plain sqlite3.connect raises
    # "no such module: vec0").
    conn = open_vec_db(str(db_path))
    try:
        vec_rows = int(conn.execute(f"SELECT COUNT(*) FROM {VEC_TABLE}").fetchone()[0])
        imported_ids = int(
            conn.execute(
                f"SELECT COUNT(DISTINCT image_id) FROM {VEC_TABLE}"
            ).fetchone()[0]
        )
    finally:
        conn.close()

    import turbovec

    idx = turbovec.IdMapIndex.load(str(DEFAULT_INDEX_PATH))
    idx_rows = len(idx)

    ok = vec_rows == idx_rows == imported_ids and vec_rows > 0
    return {
        "check": "store_parity",
        "vec_siglip_1152": vec_rows,
        "idx_rows": idx_rows,
        "imported_ids": imported_ids,
        "idx_path": str(DEFAULT_INDEX_PATH),
        "pass": ok,
    }


def run_store_parity(db_path: str | Path) -> int:
    """Run the store-parity gate, print the verdict, return an exit code."""
    rep = validate_store_parity(db_path)
    v, i, n = rep["vec_siglip_1152"], rep["idx_rows"], rep["imported_ids"]
    print(f"vec_siglip_1152 rows : {v}")
    print(f".idx rows            : {i}")
    print(f"imported vector ids  : {n}")
    if rep["pass"]:
        print("PARITY OK: vec_siglip_1152 == .idx == imported ids")
        return 0
    print(
        f"PARITY SKEW: vec_siglip_1152={v} .idx={i} imported_ids={n} "
        "(must be equal and non-zero)"
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Validate H100 artifacts vs local reference"
    )
    ap.add_argument(
        "--check-store-parity",
        action="store_true",
        help="Phase-0 gate: assert vec_siglip_1152 row count == turbovec .idx "
        "row count == imported vector ids (all non-zero). Reads catalog.db + "
        "the .idx; ignores the artifact/manifest args.",
    )
    ap.add_argument(
        "--db",
        default=str(REPO_ROOT / "data" / "catalog.db"),
        help="Path to catalog.db (used by --check-store-parity)",
    )
    ap.add_argument("--artifacts", help="Remote artifacts dir")
    ap.add_argument("--manifest", help="LOCAL-ONLY manifest.json")
    ap.add_argument(
        "--staging",
        help="Dir of the exact <id>.webp bytes that were uploaded",
    )
    ap.add_argument(
        "--tiers", default="0,1,2,3", help="Comma list of tiers to validate"
    )
    ap.add_argument(
        "--remote-captions-b",
        default=None,
        help="Second remote captions.jsonl for Tier-2 determinism check",
    )
    ap.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Validate only the first N ids (cheap spot-check)",
    )
    ap.add_argument("--out", default=None, help="Write the JSON report here")
    args = ap.parse_args(argv)

    if args.check_store_parity:
        return run_store_parity(args.db)

    if not (args.artifacts and args.manifest and args.staging):
        ap.error("--artifacts, --manifest and --staging are required for tier parity")

    artifacts = Path(args.artifacts)
    staging = Path(args.staging)
    manifest = json.loads(Path(args.manifest).read_text())
    ids = sorted(int(k) for k in manifest.keys())
    if args.sample:
        ids = ids[: args.sample]
    tiers = parse_tiers(args.tiers)

    report: dict[str, Any] = {"n_ids": len(ids), "tiers": sorted(tiers), "results": {}}
    if 0 in tiers:
        report["results"]["tier0"] = validate_tier0(artifacts, staging, ids)
    if 1 in tiers:
        report["results"]["tier1"] = validate_tier1(artifacts, staging, ids)
    if 2 in tiers:
        b = Path(args.remote_captions_b) if args.remote_captions_b else None
        report["results"]["tier2"] = validate_tier2(artifacts, b, ids)
    if 3 in tiers:
        report["results"]["tier3"] = validate_tier3(artifacts, staging, ids)

    # Overall pass: every non-skipped tier passes.
    passes = [
        r.get("pass") for r in report["results"].values() if r.get("pass") is not None
    ]
    report["overall_pass"] = bool(passes) and all(passes)

    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
