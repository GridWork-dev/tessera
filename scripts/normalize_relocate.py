#!/usr/bin/env python3
"""
Destructive normalize + relocate: move all content into media-pipeline/content/.

Layout:
  content/library/<person_slug>/unrated/<hash[:12]>.<ext>   <- images
  content/library/<person_slug>/videos/<hash[:12]>.<ext>    <- videos
  content/_unsorted/unrated/<hash[:12]>.<ext>               <- generic-folder images
  content/_unsorted/videos/<hash[:12]>.<ext>                <- generic-folder videos

Junk (filtered out, left in place or deleted with --delete-junk):
  *.txt, __MACOSX/, .DS_Store, ._*, Thumbs.db

Person derived from top-level folder name. Generic folders (Pics, pics(1))
routed to _unsorted. Filename = content SHA-256[:12] (dedup-aware, collision-free).

Default = DRY RUN. Pass --execute to move. Pass --delete-junk to remove junk.
"""

import hashlib
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/Users/liamt/Downloads/untitled folder")
REPO = ROOT / "media-pipeline"
CONTENT = REPO / "content"

IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"}
VID_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi"}
JUNK_NAMES = {".ds_store", "thumbs.db", "ehthumbs.db"}
JUNK_EXT = {".txt"}

# Top-level dirs to skip entirely (not content)
SKIP_TOP = {
    "media-pipeline",
    "sessions",
    "skills",
    "sources",
    ".agents",
    ".serena",
    ".git",
}
# Generic content folders -> _unsorted
GENERIC_FOLDERS = {"Pics", "pics (1)"}

# Stray root files that are design artifacts, not content
KEEP_AT_ROOT = {"lumen-browse.png", "lumen-dashboard.png", "lumen-grids.png"}


def slugify(name: str) -> str:
    """Person folder name -> filesystem-safe slug."""
    s = name.strip().replace(" ", "_")
    s = re.sub(r"[^\w\-]", "", s)
    return s or "unknown"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def classify(path: Path):
    """Return ('image'|'video'|'junk', ext)."""
    name = path.name.lower()
    if name in JUNK_NAMES:
        return ("junk", path.suffix)
    if "__macosx" in path.parts:
        return ("junk", path.suffix)
    if name.startswith("._"):
        return ("junk", path.suffix)
    ext = path.suffix.lower()
    if ext in JUNK_EXT:
        return ("junk", ext)
    if ext in IMG_EXTS:
        return ("image", ext)
    if ext in VID_EXTS:
        return ("video", ext)
    return ("other", ext)


def scan():
    """Walk root, classify every file, return a list of plan dicts."""
    plan = []
    top_dirs = [d for d in ROOT.iterdir() if d.is_dir() and d.name not in SKIP_TOP]

    for top in top_dirs:
        is_generic = top.name in GENERIC_FOLDERS
        person_slug = "_unsorted" if is_generic else slugify(top.name)
        bucket = "_unsorted" if is_generic else top.name

        for path in top.rglob("*"):
            if not path.is_file():
                continue
            kind, ext = classify(path)
            if kind == "junk":
                plan.append(
                    {
                        "src": path,
                        "kind": "junk",
                        "ext": ext,
                        "dst": None,
                        "bucket": bucket,
                    }
                )
                continue
            if kind == "other":
                plan.append(
                    {
                        "src": path,
                        "kind": "other",
                        "ext": ext,
                        "dst": None,
                        "bucket": bucket,
                    }
                )
                continue
            plan.append(
                {
                    "src": path,
                    "kind": kind,  # image | video
                    "ext": ext,
                    "person_slug": person_slug,
                    "bucket": bucket,
                }
            )

    # Stray root files
    for path in ROOT.iterdir():
        if path.is_file() and path.name not in KEEP_AT_ROOT:
            kind, ext = classify(path)
            if kind in ("image", "video"):
                plan.append(
                    {
                        "src": path,
                        "kind": kind,
                        "ext": ext,
                        "person_slug": "_unsorted",
                        "bucket": "_unsorted",
                    }
                )
            elif kind == "junk":
                plan.append(
                    {"src": path, "kind": "junk", "dst": None, "bucket": "_unsorted"}
                )

    return plan


def main():
    execute = "--execute" in sys.argv
    delete_junk = "--delete-junk" in sys.argv

    print("Scanning content (this computes hashes for media files)...\n")
    plan = scan()

    media = [p for p in plan if p["kind"] in ("image", "video")]
    junk = [p for p in plan if p["kind"] == "junk"]
    other = [p for p in plan if p["kind"] == "other"]

    # Compute hashes + build targets
    by_short = defaultdict(list)  # hash[:12] -> [items]
    hash_collisions = []
    content_collisions = 0

    for i, item in enumerate(media):
        h = sha256_of(item["src"])
        item["hash"] = h
        short = h[:12]
        by_short[short].append(item)
        if (i + 1) % 2000 == 0:
            print(f"  hashed {i + 1}/{len(media)} files...")

    # Resolve collisions: same short prefix
    for short, items in by_short.items():
        unique_hashes = {it["hash"] for it in items}
        if len(unique_hashes) > 1:
            hash_collisions.append((short, len(items), len(unique_hashes)))
            # extend to full hash for these
            for it in items:
                it["name"] = it["hash"]  # full hash
        else:
            # all same content -> dedup (keep one)
            if len(items) > 1:
                content_collisions += len(items) - 1
            for it in items:
                it["name"] = short

    # Build dest paths (first occurrence wins for dups)
    seen_content = {}  # hash -> dst
    dup_count = 0
    for item in media:
        h = item["hash"]
        if h in seen_content:
            item["dst"] = seen_content[h]
            item["is_dup"] = True
            dup_count += 1
            continue
        sub = "videos" if item["kind"] == "video" else "unrated"
        top = item["person_slug"]
        dst = (
            CONTENT
            / ("_unsorted" if top == "_unsorted" else "library")
            / top
            / sub
            / f"{item['name']}{item['ext']}"
        )
        item["dst"] = dst
        item["is_dup"] = False
        seen_content[h] = dst

    # Summary
    images = [p for p in media if p["kind"] == "image"]
    videos = [p for p in media if p["kind"] == "video"]
    by_bucket = Counter(p["bucket"] for p in media)

    print("=" * 60)
    print("DRY RUN SUMMARY" + ("  [EXECUTE MODE]" if execute else ""))
    print("=" * 60)
    print(f"Images:          {len(images):>7}")
    print(f"Videos:          {len(videos):>7}")
    print(f"Content dups:    {dup_count:>7}  (same hash, will collapse to 1)")
    print(f"Junk files:      {len(junk):>7}  (txt, .DS_Store, __MACOSX, ._*)")
    print(f"Other (skipped): {len(other):>7}")
    print()
    print("By source folder:")
    for bucket, n in by_bucket.most_common():
        print(f"  {bucket:<22} {n:>6}")
    print()
    print(
        f"Hash-prefix collisions (different content, same [:12]): {len(hash_collisions)}"
    )
    if hash_collisions:
        print("  (these use full hash as filename — auto-resolved)")
    print()

    # Sample targets
    print("Sample targets (first 8 media files):")
    for item in media[:8]:
        tag = " [DUP->skip]" if item.get("is_dup") else ""
        rel_dst = item["dst"].relative_to(REPO) if item["dst"] else "?"
        print(f"  {item['src'].name[:30]:<30} -> {rel_dst}{tag}")
    print()

    if other:
        print("OTHER files (not image/video/junk — will be left in place):")
        seen_ext = Counter(p["ext"] for p in other)
        for ext, n in seen_ext.most_common(15):
            print(f"  {ext or '(no ext)':<10} {n}")
        print()

    if not execute:
        print("=" * 60)
        print("DRY RUN ONLY. Re-run with --execute to move files.")
        print("Add --delete-junk to also delete junk files.")
        print("=" * 60)
        return

    # EXECUTE
    print("\nEXECUTING...\n")
    CONTENT.mkdir(parents=True, exist_ok=True)
    moved = 0
    errors = []

    for item in media:
        if item.get("is_dup"):
            continue  # skip dups
        dst = item["dst"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            continue  # already there (idempotent)
        try:
            shutil.move(str(item["src"]), str(dst))
            moved += 1
            if moved % 2000 == 0:
                print(f"  moved {moved} files...")
        except Exception as e:
            errors.append((item["src"], str(e)))

    if delete_junk:
        deleted = 0
        for item in junk:
            try:
                item["src"].unlink()
                deleted += 1
            except Exception as e:
                errors.append((item["src"], f"junk delete: {e}"))
        print(f"Deleted {deleted} junk files.")

    print(f"\nMoved {moved} media files.")
    if errors:
        print(f"ERRORS ({len(errors)}):")
        for src, err in errors[:20]:
            print(f"  {src}: {err}")
    else:
        print("No errors.")


if __name__ == "__main__":
    main()
