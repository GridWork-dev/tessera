#!/usr/bin/env python3
"""
Batch tagger with warm-start keepalive and result export.

Tags N untagged images through the configured tier set, saves to DB, and exports
full results as JSON for manual quality review.

Tiers (``--tiers``, default '2' = today's VLM-only behavior):
    0  WD-EVA02 + JoyTag structured tags  (pipeline.tier0_tagger.Tier0Tagger)
    1  SigLIP SO400M embeddings           (better as a separate pass: --embed)
    2  Ollama Qwen2.5-VL caption/tags      (pipeline.tagger.OllamaTagger)
    3  NudeNet region metadata             (pipeline.tier3_nudenet.Tier3NudeNet)

NudeNet (tier 3) is metadata only — it records regions and NEVER gates the VLM
(ADR-0001). All requested tiers run on every image independently.

Usage:
    python batch_tag.py --count 10                 # VLM-only (tier 2), save, export
    python batch_tag.py --count 50 --tiers 0,3     # WD/JoyTag tags + NudeNet regions
    python batch_tag.py --count 100 --tiers 0,2,3  # full per-image pass
    python batch_tag.py --embed --count 500        # Tier 1 SigLIP embedding pass
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).parent))

from pipeline.database import Database, apply_sqlite_pragmas
from pipeline.paths import resolve_image_path
from pipeline.settings import settings_from_config_file
from pipeline.tag_runner import (
    clear_tier0_tags,
    extract_wd_rating,
    finalize_image,
    select_unprocessed_images,
)
from pipeline.tagger import OllamaTagger


def backup_db(db_path: Path) -> None:
    """WAL-safe backup before any real DB write.

    Uses scripts/backup_db.sh (sqlite3 .backup + integrity_check + gzip). Plain
    cp/shutil.copy2 is UNSAFE with WAL mode (can capture a torn snapshot) — see
    the project guidelines. db_path is accepted for signature stability; the script targets the
    canonical data/catalog.db.
    """
    import subprocess

    script = Path(__file__).resolve().parent / "scripts" / "backup_db.sh"
    subprocess.run(["bash", str(script)], check=True)
    print("🗄️  Backed up database (scripts/backup_db.sh, WAL-safe)")


def parse_tiers(raw: str) -> set[int]:
    """Parse a comma list like '0,2,3' -> {0, 2, 3}."""
    return {int(t.strip()) for t in raw.split(",") if t.strip() != ""}


def warm_start(tagger: OllamaTagger) -> float:
    """Ping Ollama to preload the model into memory. Returns warm-up time in seconds."""
    print("🔥 Warming up Ollama model...")
    start = time.time()
    # Simple ping to ensure model is loaded
    import requests

    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": tagger.model_name,
                "prompt": "ping",
                "stream": False,
                "keep_alive": -1,
            },
            timeout=30,
        )
        elapsed = time.time() - start
        if resp.ok:
            print(f"   Model ready in {elapsed:.1f}s")
        else:
            print(f"   ⚠️ Warm-up returned {resp.status_code}")
    except Exception as e:
        elapsed = time.time() - start
        print(f"   ⚠️ Warm-up ping failed: {e}")
    return elapsed


def main():
    parser = argparse.ArgumentParser(description="Batch tag images across tiers")
    parser.add_argument("--count", type=int, default=10, help="Number of images to tag")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument(
        "--tiers",
        default="2",
        help="Comma list of tiers to run (0=WD/JoyTag, 2=VLM, 3=NudeNet). "
        "Default '2' preserves VLM-only behavior. Tier 1 is a separate --embed pass.",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Tier 1 SigLIP SO400M embedding pass (separate from the per-image loop).",
    )
    parser.add_argument(
        "--caption",
        action="store_true",
        help="Tier 2 mlx Qwen2.5-VL caption pass (separate from the per-image loop).",
    )
    parser.add_argument(
        "--ratings",
        default=None,
        help="Comma list of WD rating values to scope a --caption sweep, "
        "e.g. 'explicit,questionable'.",
    )
    parser.add_argument(
        "--export-only", action="store_true", help="Export JSON but don't save to DB"
    )
    parser.add_argument("--skip-db", action="store_true", help="Don't save to database")
    parser.add_argument(
        "--resume", action="store_true", help="Resume from last checkpoint"
    )
    parser.add_argument(
        "--person",
        default=None,
        help="Restrict the pass to one person folder (priority/per-person runs).",
    )
    args = parser.parse_args()

    # Resolve config via the typed settings layer (honors --config / env).
    cfg = settings_from_config_file(args.config)
    project_root = cfg.project_root
    db_path = cfg.database_path

    # Whether this run will write to the DB at all (gates the mandatory backup).
    writes_db = not args.skip_db and not args.export_only

    # Initialize
    db = Database(str(db_path))

    # ── Tier 1 embedding pass (separate from the per-image tagging loop) ──
    if args.embed:
        if writes_db:
            backup_db(db_path)
        from pipeline.tier1_embedder import Tier1Embedder

        print(f"\n🧭 Tier 1 SigLIP SO400M embedding pass (limit {args.count})...")
        embedder = Tier1Embedder()
        n = embedder.embed_unprocessed(db, limit=args.count, db_path=str(db_path))
        print(f"   Embedded {n} images.")
        print("\n✅ Done.")
        return

    # ── Tier 2 caption pass (separate; idempotent + per-image commit) ──
    # No auto-backup here: the pass is append-only INSERT OR IGNORE and the
    # launchd sweep calls it repeatedly; the staged ramp does one cp per stage.
    if args.caption:
        from pipeline.tier2_captioner import Tier2Captioner

        cap = Tier2Captioner()
        if not cap.health():
            print(f"❌ mlx VLM server not healthy at {cap.base_url} — start it first.")
            return
        rating_values = (
            [r.strip() for r in args.ratings.split(",") if r.strip()]
            if args.ratings
            else None
        )
        print(
            f"\n🗣️  Tier 2 caption pass (limit {args.count}, "
            f"person={args.person}, ratings={rating_values})..."
        )
        n = cap.caption_unprocessed(
            db, limit=args.count, person=args.person, rating_values=rating_values
        )
        print(f"   Captioned {n} images.")
        print("\n✅ Done.")
        return

    tiers = parse_tiers(args.tiers)

    # Tier 0 / Tier 3 taggers (constructed only when requested; lazy heavy imports).
    tier0 = None
    if 0 in tiers:
        from pipeline.tier0_tagger import Tier0Tagger

        tier0 = Tier0Tagger()
    tier3 = None
    if 3 in tiers:
        from pipeline.tier3_nudenet import Tier3NudeNet

        tier3 = Tier3NudeNet()

    # Back up before any real per-image DB write (skipped for --skip-db/--export-only).
    if writes_db:
        backup_db(db_path)

    tagger = OllamaTagger(model_name="qwen2.5vl:7b-8k", device="mps")

    print(f"\n{'=' * 60}")
    print(f"BATCH TAGGER — {args.count} images")
    print(f"{'=' * 60}")

    run_vlm = 2 in tiers

    # Check Ollama (only needed when the VLM tier is active).
    warm_time = 0.0
    if run_vlm:
        if not tagger.load_model():
            print("❌ Ollama connection failed. Make sure ollama serve is running.")
            return
        warm_time = warm_start(tagger)

    # Get unprocessed images — deterministic id order, restart-safe (processed=0
    # is the resume key; the loop sets processed=1 per image after the requested
    # fast tiers write). NOT ORDER BY RANDOM().
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    apply_sqlite_pragmas(conn)
    images = select_unprocessed_images(conn, args.count, person=args.person)
    conn.close()

    if not images:
        print("❌ No unprocessed images found (all processed=1 for this scope)!")
        return

    print(f"\n📸 Tagging {len(images)} images (tiers {sorted(tiers)})...")
    print(f"{'─' * 60}")

    results = []
    total_time = 0
    success_count = 0
    error_count = 0
    pre_filtered_count = 0  # retained for export/stats compatibility (always 0 now)

    # Per-image DB session for tier 0 / tier 3 writes (committed inside their writers).
    tier_session = (
        db.get_session()
        if (tier0 is not None or tier3 is not None) and writes_db
        else None
    )

    for i, (img_id, img_path, _filename, person) in enumerate(images):
        # FIX: img_path is RELATIVE to the content root — resolve it ONCE here.
        # (Previously this did Path(img_path) and treated the relative path as
        # absolute, so .exists() was always False.)
        path = resolve_image_path(img_path)
        if not path.exists():
            print(f"  [{i + 1}/{len(images)}] ⚠️ File not found: {img_path}")
            error_count += 1
            continue

        print(f"  [{i + 1}/{len(images)}] {person}: {path.name[:60]}...")

        # Per-image fast-tier state. "ok" means "nothing to do or it succeeded";
        # finalize (processed=1) only happens when EVERY requested fast tier is ok,
        # so a crash never marks an image done with missing tags.
        wd_rating: str | None = None
        tier0_ok = tier0 is None or tier_session is None
        tier3_ok = tier3 is None

        # ── Tier 0: WD-EVA02 + JoyTag structured tags ───────────────────
        if tier0 is not None:
            try:
                start = time.time()
                if tier_session is not None:
                    # Re-tag safety: drop stale Tier-0 rows so the current
                    # threshold + tag_source schema apply cleanly (no-op if none).
                    clear_tier0_tags(tier_session, img_id)
                    rows = tier0.tag_image(img_path, tier_session, img_id, db)
                    wd_rating = extract_wd_rating(rows)
                    tier0_ok = True
                    print(
                        f"     🏷️  Tier0: {len(rows)} scored tags "
                        f"({time.time() - start:.2f}s)"
                    )
                else:
                    print("     🏷️  Tier0: skipped DB write (--skip-db/--export-only)")
            except Exception as e:
                if tier_session is not None:
                    tier_session.rollback()  # undo the pending stale-row DELETE
                print(f"     ⚠️ Tier0 error: {e}")

        # ── Tier 3: NudeNet region metadata (NEVER a gate) ──────────────
        if tier3 is not None:
            try:
                start = time.time()
                regions = tier3.detect_image(img_path)
                if tier_session is not None:
                    tier3.write_regions(tier_session, img_id, regions)
                tier3_ok = True
                print(
                    f"     🧭 Tier3: {len(regions)} regions "
                    f"({time.time() - start:.2f}s)"
                )
            except Exception as e:
                print(f"     ⚠️ Tier3 (NudeNet) error: {e}")

        # ── A4: mark processed + derive rating (the idempotent resume key) ──
        if tier_session is not None and tier0_ok and tier3_ok:
            finalize_image(tier_session, img_id, wd_rating)
            tier_session.commit()

        # ── Tier 2: VLM analysis with retry ─────────────────────────────
        if not run_vlm:
            # No VLM this run; tiers 0/3 already wrote. Only count a success when a
            # DB write actually happened (not in --skip-db/--export-only dry runs).
            if tier_session is not None:
                success_count += 1
            results.append(
                {
                    "_image_id": img_id,
                    "_person_folder": person,
                    "_tiers": sorted(tiers),
                }
            )
            continue

        result: dict[str, Any] | None = None
        elapsed = 0.0
        for attempt in range(2):
            start = time.time()
            try:
                result = tagger.analyze_image(path)
                elapsed = time.time() - start
                total_time += elapsed
                break  # success, exit retry loop
            except Exception as e:
                elapsed = time.time() - start
                err_msg = str(e)
                if attempt == 0 and (
                    "timeout" in err_msg.lower() or "timed out" in err_msg.lower()
                ):
                    print("     ⏰ Timeout (attempt 1), retrying with extended wait...")
                    # Increase Ollama request timeout for retry. OllamaTagger's
                    # timeout is runtime-defined on some legacy versions.
                    tagger_any = cast(Any, tagger)
                    tagger_any.timeout = getattr(tagger_any, "timeout", 120) * 2
                    continue
                total_time += elapsed
                print(
                    f"     ❌ {'Timeout' if 'timeout' in err_msg.lower() else 'Error'}: {err_msg[:80]}"
                )
                error_count += 1
                result = {
                    "_image_id": img_id,
                    "_person_folder": person,
                    "_elapsed_sec": round(elapsed, 2),
                    "error": err_msg,
                }
                break

        if result is None:
            error_count += 1
            results.append(
                {
                    "_image_id": img_id,
                    "_person_folder": person,
                    "error": "max retries exceeded",
                }
            )
            continue

        if "error" in result:
            print(f"     ❌ VLM error: {result['error']}")
            results.append(result)
            continue

        # ── Checkpoint progress ────────────────────────────────────────
        checkpoint_path = project_root / "data" / "batch_progress.json"
        checkpoint_path.write_text(
            json.dumps(
                {
                    "timestamp": datetime.now().isoformat(),
                    "processed": i + 1,
                    "success": success_count,
                    "errors": error_count,
                    "vlm_analyzed": success_count,
                    "total_time_sec": round(total_time, 1),
                    "last_image_id": img_id,
                }
            )
        )

        result["_image_id"] = img_id
        result["_elapsed_sec"] = round(elapsed, 2)
        result["_person_folder"] = person

        # Show key tags
        rating = result.get("rating", "?")
        content = result.get("content_type", "?")
        pose = result.get("pose", "?")
        setting = result.get("setting", "?")
        clothing = ", ".join(result.get("clothing", [])[:3])
        corrections = result.get("_corrections", [])

        status = f"     ✅ {rating} | {content} | {pose} | {setting}"
        if clothing:
            status += f" | 👕 {clothing}"
        if corrections:
            status += f"\n     🔧 Corrections: {corrections}"
        print(status)
        success_count += 1
        results.append(result)

    # Close the tier 0/3 session (commits already happened inside the writers).
    if tier_session is not None:
        try:
            tier_session.commit()
        finally:
            tier_session.close()

    # Stats
    vlm_count = success_count
    avg_time = total_time / max(len(images), 1)
    pre_filter_rate = 0.0

    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")
    print(f"  Total images:      {len(images)}")
    print(f"  Successful:        {success_count}")
    print(f"    VLM analyzed:    {vlm_count if run_vlm else 0}")
    print(f"  Errors:            {error_count}")
    print(f"  Total time:        {total_time:.1f}s")
    print(f"  Avg per image:     {avg_time:.1f}s")
    print(f"  Warm-up time:      {warm_time:.1f}s")
    if success_count > 0 and total_time > 0:
        # Derive the remaining count from the DB (the old 13924 literal was stale
        # vs the real 26,590-image corpus). total_time only accrues VLM time, so
        # this estimate is meaningful for VLM runs and skipped for fast-tier runs.
        import sqlite3 as _sqlite3

        _c = _sqlite3.connect(str(db_path))
        remaining = _c.execute(
            "SELECT COUNT(*) FROM images WHERE processed = 0"
        ).fetchone()[0]
        _c.close()
        est_backlog = remaining / success_count * total_time
        print(
            f"  Est. full backlog: {est_backlog / 3600:.1f} hours ({remaining} remaining)"
        )

    # Export JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = project_root / "data" / "samples"
    export_dir.mkdir(parents=True, exist_ok=True)
    export_path = export_dir / f"batch_tag_{timestamp}.json"

    with open(export_path, "w") as f:
        json.dump(
            {
                "run_info": {
                    "timestamp": timestamp,
                    "model": tagger.model_name,
                    "count": len(images),
                    "success_count": success_count,
                    "error_count": error_count,
                    "pre_filtered_count": pre_filtered_count,
                    "pre_filter_rate_pct": round(pre_filter_rate, 1),
                    "vlm_analyzed_count": vlm_count,
                    "total_time_sec": round(total_time, 1),
                    "avg_time_sec": round(avg_time, 1),
                    "warmup_time_sec": round(warm_time, 1),
                },
                "results": results,
            },
            f,
            indent=2,
        )
    print(f"\n💾 Exported results to: {export_path}")

    # Save to DB — legacy VLM-only path. Runs ONLY for a pure VLM run (run_vlm
    # and no fast-tier session). When Tier-0/Tier-3 ran, finalize_image() in the
    # per-image loop is the SOLE authority on `processed` (gated on tier success),
    # so this block must NOT touch it — otherwise a Tier-0-failed image would be
    # wrongly marked processed=1 and stranded forever (review CRITICAL).
    if (
        run_vlm
        and tier_session is None
        and not args.skip_db
        and not args.export_only
        and success_count > 0
    ):
        print(f"\n💾 Saving {success_count} results to database...")
        with db.get_session() as session:
            saved = 0
            for r in results:
                if "error" not in r and "_image_id" in r:
                    img_id = r["_image_id"]
                    # Convert result to tag format
                    tags = {}
                    for key in [
                        "person",
                        "clothing",
                        "content_type",
                        "pose",
                        "composition",
                        "setting",
                        "location",
                        "lighting",
                        "mood",
                        "rating",
                        "tags",
                    ]:
                        val = r.get(key)
                        if val:
                            if isinstance(val, list):
                                tags[key] = [str(v) for v in val]
                            else:
                                tags[key] = str(val)

                    try:
                        confidence = float(r.get("confidence", 1.0))
                        db.add_tags(session, img_id, tags, confidence=confidence)
                        # Never mark processed without real tags (defense-in-depth).
                        if tags:
                            from pipeline.database import Image

                            session.query(Image).filter(Image.id == img_id).update(
                                {"processed": True}
                            )
                            saved += 1
                    except Exception as e:
                        print(f"   ⚠️ Failed to save image {img_id}: {e}")

            session.commit()
            print(f"   Saved {saved} images to database")

    # Tag diversity report
    if success_count > 0:
        print(f"\n{'─' * 60}")
        print("TAG DIVERSITY REPORT")
        print(f"{'─' * 60}")
        categories = [
            "rating",
            "content_type",
            "pose",
            "setting",
            "location",
            "lighting",
            "mood",
        ]
        for cat in categories:
            values = {}
            for r in results:
                if "error" not in r:
                    val = r.get(cat, "?")
                    if val:
                        values[str(val)] = values.get(str(val), 0) + 1
            if values:
                unique = len(values)
                print(f"  {cat}: {unique} unique values")
                for v, count in sorted(
                    values.items(), key=lambda x: x[1], reverse=True
                )[:5]:
                    bar = "█" * count
                    print(f"    {v:20s} {bar} ({count})")

    print("\n✅ Done.")


if __name__ == "__main__":
    main()
