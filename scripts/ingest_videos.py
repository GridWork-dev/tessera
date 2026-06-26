#!/usr/bin/env python3
"""Ingest videos into the catalog, then detect per-clip scenes.

CLI runner for the video pillar — wraps the (tested) pipeline functions into one
resumable command:

  Stage 1  pipeline.video_ingest.ingest_videos
           walk content root -> hash -> probe -> poster -> insert `videos` row.
           Resumable (skip by hash/path) and quarantine-safe (a bad file gets
           processed=-1, never aborts the walk).
  Stage 2  pipeline.scene_detect.detect_and_persist  (skip with --no-scenes)
           detect + persist `video_scenes` for each processed clip that has none
           (powers the player timeline scene chips). Resumable + degrades if the
           scenedetect package is missing.

catalog.db is the source of truth: this WRITES to it, so it backs up first via
scripts/backup_db.sh (WAL-safe) unless --skip-backup.

Run AFTER clips land in the content root (default: content/, e.g.
content/_inbound_videos/).

  ./venv/bin/python scripts/ingest_videos.py                # ingest + scenes
  ./venv/bin/python scripts/ingest_videos.py --limit 50     # cap NEW rows
  ./venv/bin/python scripts/ingest_videos.py --no-scenes    # ingest only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.database import Database, Video  # noqa: E402
from pipeline.paths import content_root, resolve_image_path  # noqa: E402
from pipeline.settings import settings_from_config_file  # noqa: E402
from pipeline.video_ingest import (  # noqa: E402
    SUPPORTED_VIDEO_EXTENSIONS,
    ingest_videos,
)


def backup_db() -> None:
    """WAL-safe backup via scripts/backup_db.sh before any write."""
    script = Path(__file__).resolve().parent / "backup_db.sh"
    print("💾 Backing up catalog.db (scripts/backup_db.sh)…")
    subprocess.run(["bash", str(script)], check=True)


def check_manifest(root: Path) -> dict | None:
    """Validate the handoff against ``_inbound_videos/manifest.csv`` if present.

    The manifest (model,filename,bytes,...) is the transfer's ground truth. Each
    file must exist at ``_inbound_videos/<model>/<filename>`` with size == bytes —
    a size mismatch means the file is still being copied (rsync in flight). Returns
    ``{present, missing, mismatch, total}`` or ``None`` when no manifest exists
    (older handoff / can't validate completeness).
    """
    import csv

    manifest = root / "_inbound_videos" / "manifest.csv"
    if not manifest.exists():
        manifest = root / "manifest.csv"
    if not manifest.exists():
        return None

    present = missing = mismatch = total = 0
    with open(manifest, newline="") as f:
        for row in csv.DictReader(f):
            total += 1
            model = (row.get("model") or "").strip()
            name = (row.get("filename") or "").strip()
            try:
                want = int(row.get("bytes") or 0)
            except ValueError:
                want = 0
            fp = root / "_inbound_videos" / model / name
            if not fp.exists():
                missing += 1
            elif want and fp.stat().st_size != want:
                mismatch += 1
            else:
                present += 1
    return {
        "present": present,
        "missing": missing,
        "mismatch": mismatch,
        "total": total,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest videos + detect scenes.")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap NEW video rows added (resume-skips don't count).",
    )
    ap.add_argument(
        "--content-root",
        default=None,
        help="Override content root (default: the repo content/ dir).",
    )
    ap.add_argument(
        "--poster-dir",
        default=None,
        help="Poster output dir (default: <content-root>/_posters).",
    )
    ap.add_argument(
        "--no-scenes", action="store_true", help="Skip scene detection (ingest only)."
    )
    ap.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip the pre-write DB backup (NOT recommended).",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Ingest even if the manifest completeness check fails (transfer "
        "may be mid-flight — risks ingesting partial files as processed=1).",
    )
    args = ap.parse_args()

    db_path = settings_from_config_file(args.config).database_path

    root = Path(args.content_root) if args.content_root else content_root()
    if not root.exists():
        print(f"❌ Content root not found: {root}")
        return 1

    clips = [
        p
        for p in root.rglob("*")
        if p.is_file()
        and not p.name.startswith(".")
        and p.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS
    ]
    print(f"📂 Content root: {root}")
    print(f"🎞️  {len(clips)} video file(s) found under content root.")
    if not clips:
        print(
            "   Nothing to ingest. Land clips first "
            "(e.g. content/_inbound_videos/), then re-run."
        )
        return 0

    # Completeness gate: never ingest a half-transferred file. ingest is
    # resume-skip-by-path, so a partial ingested once stays wrong forever.
    status = check_manifest(root)
    if status is not None:
        print(
            f"📋 Manifest: {status['present']}/{status['total']} present "
            f"({status['missing']} missing, {status['mismatch']} size-mismatch)."
        )
        incomplete = status["missing"] > 0 or status["mismatch"] > 0
        if incomplete and not args.force:
            print(
                "⏳ Transfer looks incomplete (rsync may still be running). "
                "Re-run when it finishes, or pass --force to ingest anyway."
            )
            return 1
    else:
        print("📋 No manifest.csv found — skipping completeness check.")

    if not args.skip_backup:
        backup_db()

    db = Database(str(db_path))

    print("→ Stage 1: ingest (hash · probe · poster · insert) …")
    counts = ingest_videos(db, root, limit=args.limit, poster_dir=args.poster_dir)
    print(
        f"   added={counts['added']} skipped={counts['skipped']} "
        f"quarantined={counts['quarantined']}"
    )

    if args.no_scenes:
        print("→ Stage 2: scenes SKIPPED (--no-scenes).")
        return 0

    try:
        from pipeline.scene_detect import detect_and_persist
    except ImportError as exc:
        print(
            f"⚠️  Scene detection unavailable ({exc}). "
            "Install scenedetect to enable. Ingest is complete."
        )
        return 0

    with db.get_session() as session:
        targets = [
            (v.id, v.path)
            for v in session.query(Video).filter(Video.processed == 1).all()
        ]
    print(f"→ Stage 2: scene detection over {len(targets)} processed clip(s) …")
    scened = already = failed = 0
    for vid, rel in targets:
        try:
            written = detect_and_persist(db, vid, resolve_image_path(rel))
            if written > 0:
                scened += 1
            else:
                already += 1
        except Exception as exc:  # never abort the whole pass
            failed += 1
            print(f"   ⚠️  scene detect failed for video {vid} ({rel}): {exc}")
    print(f"   scened={scened} already={already} failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
