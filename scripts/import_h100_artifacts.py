#!/usr/bin/env python3
"""
H100 OFFLOAD — import returned artifacts into catalog.db (runs on the Mac).

Reads the four artifacts produced by ``remote_pipeline_runner.py`` (all keyed by
the integer image id), maps each temp id back to the catalog ``image_id`` via the
LOCAL-ONLY ``manifest.json`` written by ``prepare_remote_upload.py``, and writes
the results into ``catalog.db`` by REUSING the existing pipeline methods so the
imported rows are byte-identical to what local processing would have produced.

Mapping note: the box used the catalog primary key as the filename id, so the
temp id IS the image_id. The manifest is still consulted to (a) validate that
every returned id was actually one we shipped, and (b) reuse person/rating for
sanity logging — NEVER to set rating (rating stays owned by Tier-0/WD).

WAL-SAFETY + BACKUP
-------------------
catalog.db is the source of truth. This script:
  * runs ``scripts/backup_db.sh`` first (WAL-safe .backup + integrity_check + gzip)
    unless --skip-backup is passed;
  * opens connections with WAL + busy_timeout via apply_sqlite_pragmas;
  * NEVER migrates schema (tables/columns must already exist — captions table,
    nudenet_regions column, the vec_siglip_1152 table is created via the existing
    ensure_vec_table helper).

Per-tier import (mirrors research brief 06):
  Tier 0  tags.jsonl     -> Database.add_tags_scored (idempotent UPSERT)
  Tier 1  embeddings.npy -> TurboVecStore.add + ensure_vec_table + upsert_vec
                            (builds the .idx LOCALLY so the format stays Mac-owned)
  Tier 2  captions.jsonl -> INSERT OR IGNORE INTO captions (model=
                            "llama-joycaption-beta-one")
  Tier 3  nudenet.jsonl  -> Tier3NudeNet.write_regions (nudenet_regions JSON +
                            nudenet_checked=1; NEVER sets rating)

Usage:
  python3 scripts/import_h100_artifacts.py \
      --artifacts outputs/h100/<stamp>/artifacts \
      --manifest  outputs/h100/<stamp>/manifest.json \
      --tiers 0,1,2,3

Dry run (parse + validate, no writes):
  python3 scripts/import_h100_artifacts.py --artifacts ... --manifest ... --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DB = REPO_ROOT / "data" / "catalog.db"

JOYCAPTION_DB_MODEL = "llama-joycaption-beta-one"


def load_manifest(path: Path) -> dict[int, dict[str, Any]]:
    """Load the LOCAL-ONLY id->meta manifest, keyed back to int ids."""
    raw = json.loads(path.read_text())
    return {int(k): v for k, v in raw.items()}


def iter_jsonl(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def run_backup(db_path: Path) -> None:
    """WAL-safe backup via scripts/backup_db.sh before any write."""
    script = REPO_ROOT / "scripts" / "backup_db.sh"
    print(f"  backing up {db_path} via {script.name} ...")
    subprocess.run(["bash", str(script), str(db_path)], check=True, cwd=str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Tier 0 — scored tags.
# ---------------------------------------------------------------------------
def import_tier0(
    db, path: Path, valid_ids: set[int], dry_run: bool, run_id: int | None = None
) -> int:
    if not path.exists():
        print(f"  tier0: {path} not found, skipping")
        return 0
    from pipeline.tag_runner import extract_wd_rating, finalize_image

    n = 0
    skipped = 0
    with db.get_session() as session:
        for obj in iter_jsonl(path):
            img_id = int(obj["id"])
            if img_id not in valid_ids:
                skipped += 1
                continue
            rows = obj.get("rows", [])
            if not rows:
                continue
            if not dry_run:
                # Reuse the EXACT method tier0_tagger.tag_image uses (idempotent
                # UPSERT on image_id,category,value,tag_source). run_id stamps the
                # provenance (migration 007) when a run manifest was supplied.
                db.add_tags_scored(session, img_id, rows, run_id=run_id)
                # Mirror tag_runner.finalize_image: mark processed + assign the
                # Rating label (label set, via _assign_rating_label) from the
                # WD-EVA02 rating head. Without this the imported rows stay
                # processed=0 with no Rating label despite being fully tagged.
                finalize_image(session, img_id, extract_wd_rating(rows))
            n += 1
        if not dry_run:
            session.commit()
    print(f"  tier0: imported {n} images ({skipped} unknown ids skipped)")
    return n


# ---------------------------------------------------------------------------
# Tier 1 — embeddings -> turbovec .idx (local) + sqlite-vec rescore table.
# ---------------------------------------------------------------------------
def import_tier1(
    db, artifacts: Path, valid_ids: set[int], db_path: Path, dry_run: bool
) -> int:
    emb_path = artifacts / "embeddings.npy"
    ids_path = artifacts / "ids.npy"
    if not emb_path.exists() or not ids_path.exists():
        print(f"  tier1: {emb_path.name}/{ids_path.name} not found, skipping")
        return 0

    from pipeline.tier1_embedder import (
        Tier1Embedder,
        TurboVecStore,
        ensure_vec_table,
        l2_normalize,
        open_vec_db,
    )

    mat = np.load(emb_path).astype(np.float32)
    ids = np.load(ids_path).astype(np.int64)
    if mat.shape[0] != ids.shape[0]:
        raise ValueError(f"embeddings/ids length mismatch: {mat.shape} vs {ids.shape}")
    if mat.shape[1] != Tier1Embedder.EMBEDDING_DIM:
        raise ValueError(
            f"embedding dim {mat.shape[1]} != expected {Tier1Embedder.EMBEDDING_DIM}"
        )

    if dry_run:
        unknown = sum(1 for i in ids if int(i) not in valid_ids)
        print(f"  tier1: dry-run, {len(ids)} vecs ({unknown} unknown ids)")
        return 0

    # Build the .idx LOCALLY (turbovec/sqlite-vec are local-only) so the index
    # format stays Mac-owned. Re-L2-normalize defensively (remote already did).
    store = TurboVecStore(dim=Tier1Embedder.EMBEDDING_DIM, bit_width=4)
    conn = open_vec_db(db_path)
    n = 0
    skipped = 0
    try:
        ensure_vec_table(conn)
        for img_id_np, row in zip(ids, mat):
            img_id = int(img_id_np)
            if img_id not in valid_ids:
                skipped += 1
                continue
            vec = l2_normalize(row)
            store.add(img_id, vec)  # no-op if already present (resume-safe)
            upsert_vec_inline(conn, img_id, vec)
            n += 1
            if n % 500 == 0:
                store.save()
                conn.commit()
        store.save()
        conn.commit()
    finally:
        conn.close()
    print(f"  tier1: imported {n} embeddings ({skipped} unknown ids skipped)")
    return n


def upsert_vec_inline(conn, image_id: int, vector: np.ndarray) -> None:
    """Thin re-export of tier1_embedder.upsert_vec (kept inline for clarity)."""
    from pipeline.tier1_embedder import upsert_vec

    upsert_vec(conn, image_id, vector)


# ---------------------------------------------------------------------------
# Tier 2 — captions (model = llama-joycaption-beta-one).
# ---------------------------------------------------------------------------
def import_tier2(
    db, path: Path, valid_ids: set[int], dry_run: bool, run_id: int | None = None
) -> int:
    if not path.exists():
        print(f"  tier2: {path} not found, skipping")
        return 0
    import sqlite3

    from pipeline.database import apply_sqlite_pragmas, rebuild_caption_fts

    n = 0
    skipped = 0
    conn = sqlite3.connect(db.db_path)
    apply_sqlite_pragmas(conn)
    try:
        for obj in iter_jsonl(path):
            img_id = int(obj["id"])
            caption = (obj.get("caption") or "").strip()
            if img_id not in valid_ids:
                skipped += 1
                continue
            if not caption:
                continue
            if not dry_run:
                # Mirrors Tier2Captioner.caption_unprocessed: INSERT OR IGNORE on
                # UNIQUE(image_id, model) so JoyCaption coexists with prior rows.
                # run_id stamps provenance (migration 007) when supplied.
                conn.execute(
                    "INSERT OR IGNORE INTO captions (image_id, model, caption, run_id) "
                    "VALUES (?, ?, ?, ?)",
                    (img_id, JOYCAPTION_DB_MODEL, caption, run_id),
                )
                conn.commit()
            n += 1
        if not dry_run:
            # Rebuild-after-import (migration 008): raw INSERTs bypass SQLAlchemy
            # events, so the FTS5 index is repopulated from captions here rather
            # than via triggers. No-op if the FTS table isn't present.
            indexed = rebuild_caption_fts(conn)
            print(f"  tier2: caption FTS rebuilt -> {indexed} rows indexed")
    finally:
        conn.close()
    print(f"  tier2: imported {n} captions ({skipped} unknown ids skipped)")
    return n


# ---------------------------------------------------------------------------
# Tier 3 — NudeNet regions (metadata only).
# ---------------------------------------------------------------------------
def import_tier3(db, path: Path, valid_ids: set[int], dry_run: bool) -> int:
    if not path.exists():
        print(f"  tier3: {path} not found, skipping")
        return 0
    from pipeline.tier3_nudenet import Tier3NudeNet

    tier3 = Tier3NudeNet()  # constructed for write_regions only; no model load
    n = 0
    skipped = 0
    with db.get_session() as session:
        for obj in iter_jsonl(path):
            img_id = int(obj["id"])
            if img_id not in valid_ids:
                skipped += 1
                continue
            regions = obj.get("regions", [])
            if not dry_run:
                # write_regions sets nudenet_regions JSON + nudenet_checked=1,
                # NEVER touches rating (ADR-0001). Regions are already in stored
                # [x1,y1,x2,y2] schema (remote ran convert_regions), so pass through.
                tier3.write_regions(session, img_id, regions)
            n += 1
    print(f"  tier3: imported {n} region rows ({skipped} unknown ids skipped)")
    return n


def parse_tiers(raw: str) -> set[int]:
    return {int(t.strip()) for t in raw.split(",") if t.strip() != ""}


# Per-tier model id derived from the run_manifest (for the ModelRun provenance row).
def _tier_model_id(tier: int, manifest: dict[str, Any]) -> str | None:
    return {
        0: "wd_eva02+joytag",
        1: manifest.get("siglip_model"),
        2: manifest.get("joycaption_db_model") or manifest.get("joycaption_model"),
        3: "nudenet",
    }.get(tier)


def record_run_for_tier(
    db, manifest: dict[str, Any], base_key: str, tier: int
) -> int | None:
    """Upsert a ModelRun row for one tier from the run_manifest; return its id.

    Persists the run-level provenance the box emits (run_manifest.json) that this
    importer previously discarded (roadmap E6). One row per tier (run_key
    ``<stamp>:tier<N>``) so tags/captions get a precise FK. Returns None on any
    failure so a provenance hiccup never blocks the actual artifact import.
    """
    try:
        from pipeline.database import record_model_run

        tier_label = f"tier{tier}"
        written = (manifest.get("written") or {}).get(tier_label)
        m = dict(manifest)
        m.update(
            {
                "run_key": f"{base_key}:{tier_label}",
                "tier": tier_label,
                "model_id": _tier_model_id(tier, manifest),
                "item_count": written,
            }
        )
        with db.get_session() as session:
            run = record_model_run(session, m, tier=tier_label)
            session.commit()
            return run.id
    except Exception as exc:  # pragma: no cover - provenance is best-effort
        print(f"  warn: could not record model_run for tier{tier}: {exc}")
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Import H100 artifacts into catalog.db")
    ap.add_argument(
        "--artifacts",
        required=True,
        help="Dir with tags.jsonl/embeddings.npy/ids.npy/captions.jsonl/nudenet.jsonl",
    )
    ap.add_argument(
        "--manifest",
        required=True,
        help="LOCAL-ONLY manifest.json from prepare_remote_upload.py",
    )
    ap.add_argument(
        "--run-manifest",
        default=None,
        help="run_manifest.json from remote_pipeline_runner.py — persists run "
        "provenance into model_runs + stamps run_id on imported tags/captions",
    )
    ap.add_argument("--db", default=str(DEFAULT_DB), help="Path to catalog.db")
    ap.add_argument("--tiers", default="0,1,2,3", help="Comma list of tiers to import")
    ap.add_argument(
        "--skip-backup", action="store_true", help="Skip the WAL-safe backup"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="Parse + validate, no writes"
    )
    args = ap.parse_args(argv)

    from pipeline.database import Database

    artifacts = Path(args.artifacts)
    manifest_path = Path(args.manifest)
    db_path = Path(args.db)
    tiers = parse_tiers(args.tiers)

    if not manifest_path.exists():
        print(f"manifest not found: {manifest_path}", file=sys.stderr)
        return 2
    if not db_path.exists():
        print(f"catalog.db not found: {db_path}", file=sys.stderr)
        return 2

    manifest = load_manifest(manifest_path)
    valid_ids = set(manifest.keys())
    print(f"manifest: {len(valid_ids)} known ids")

    if not args.dry_run and not args.skip_backup:
        run_backup(db_path)

    db = Database(str(db_path))

    # Run provenance (E6): if a run_manifest is supplied, persist one ModelRun row
    # per tier and stamp imported tags/captions with its id. Base run_key is the
    # artifacts stamp dir so re-imports upsert the same rows (idempotent).
    run_manifest: dict[str, Any] = {}
    run_ids: dict[int, int | None] = {}
    if args.run_manifest:
        rm_path = Path(args.run_manifest)
        if rm_path.exists():
            run_manifest = json.loads(rm_path.read_text())
            base_key = artifacts.parent.name or artifacts.name or "h100-run"
            if not args.dry_run:
                for t in sorted(tiers):
                    run_ids[t] = record_run_for_tier(db, run_manifest, base_key, t)
                print(f"  recorded model_runs for tiers {sorted(run_ids)}")
        else:
            print(f"  warn: --run-manifest {rm_path} not found; skipping provenance")

    counts: dict[str, int] = {}
    if 0 in tiers:
        counts["tier0"] = import_tier0(
            db, artifacts / "tags.jsonl", valid_ids, args.dry_run, run_ids.get(0)
        )
    if 1 in tiers:
        counts["tier1"] = import_tier1(db, artifacts, valid_ids, db_path, args.dry_run)
    if 2 in tiers:
        counts["tier2"] = import_tier2(
            db, artifacts / "captions.jsonl", valid_ids, args.dry_run, run_ids.get(2)
        )
    if 3 in tiers:
        counts["tier3"] = import_tier3(
            db, artifacts / "nudenet.jsonl", valid_ids, args.dry_run
        )

    print(
        f"\nimport {'(dry-run) ' if args.dry_run else ''}complete: {json.dumps(counts)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
