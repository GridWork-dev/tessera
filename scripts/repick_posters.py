#!/usr/bin/env python3
"""Resumable poster re-pick: choose a better representative frame per video.

Iterates ``videos WHERE poster_locked = 0``, loads detected scenes (if any),
scores candidate frames with the heuristic scorer (pipeline.video_thumbnail),
and regenerates the poster at the chosen timestamp. Locked posters (a user's
manual pick) are never touched.

RESUMABLE / SAFE: skips when cv2 is unavailable or the scorer degrades (None),
leaving the existing poster in place — so re-running after an interruption is a
no-op for already-good videos. Reads whatever catalog the MEDIA_PIPELINE_* env
seam points at (live or staging). For the LIVE catalog, back up first:
``bash scripts/backup_db.sh``.

  ./venv/bin/python scripts/repick_posters.py [--limit N] [--dry-run]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.paths import resolve_image_path  # noqa: E402
from pipeline.settings import get_settings  # noqa: E402
from pipeline.video_ingest import generate_poster  # noqa: E402
from pipeline.video_thumbnail import pick_best_frame_time  # noqa: E402


def _pending(conn: sqlite3.Connection, limit: int | None) -> list[tuple]:
    """(id, path, poster_path, duration) for unlocked videos with a real path."""
    sql = (
        "SELECT id, path, poster_path, duration FROM videos "
        "WHERE poster_locked = 0 AND path IS NOT NULL AND processed = 1"
    )
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def _scenes(conn: sqlite3.Connection, video_id: int) -> list[tuple[float, float]]:
    rows = conn.execute(
        "SELECT start_time, end_time FROM video_scenes "
        "WHERE video_id = ? ORDER BY scene_index",
        (video_id,),
    ).fetchall()
    return [(s, e) for s, e in rows if s is not None and e is not None]


def main() -> int:
    ap = argparse.ArgumentParser(description="Re-pick video posters (Wave 2a)")
    ap.add_argument("--limit", type=int, default=None, help="Max videos to process")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Score + report the chosen timestamp without writing posters",
    )
    args = ap.parse_args()

    db_path = str(get_settings().database_path)
    print(f"[repick] db={db_path} dry_run={args.dry_run}")
    conn = sqlite3.connect(db_path)
    try:
        pending = _pending(conn, args.limit)
        print(f"[repick] {len(pending)} unlocked videos to consider")
        n_done = n_skip = 0
        for vid, path, poster_path, duration in pending:
            scenes = _scenes(conn, vid)
            src = resolve_image_path(path)
            best = pick_best_frame_time(
                str(src), float(duration or 0.0), scenes=scenes or None
            )
            if best is None:
                n_skip += 1
                continue
            if args.dry_run:
                print(f"[repick] video {vid}: would re-pick at t={best:.2f}s")
                n_done += 1
                continue
            if not poster_path:
                n_skip += 1
                continue
            out = resolve_image_path(poster_path)
            ok = generate_poster(src, out, seek=best, duration=duration)
            if ok:
                n_done += 1
            else:
                n_skip += 1
        print(f"[repick] done: {n_done} re-picked, {n_skip} skipped")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
