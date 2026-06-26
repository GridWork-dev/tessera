#!/usr/bin/env python3
"""Verify leftovers after normalize: every remaining source file must be a
content-duplicate of something already in content/. Reports any UNIQUE missed
file (real bug) vs dedup-copy (expected, safe to delete)."""

import hashlib
from pathlib import Path

ROOT = Path("/Users/liamt/Downloads/untitled folder")
CONTENT = ROOT / "media-pipeline/content"

PERSON_DIRS = [
    "Pics",
    "pics (1)",
    "Breckie Hill",
    "Piper Rockelle",
    "Lanah Cherry",
    "Bunni Emmie",
    "Ambie Bambii",
    "Elly Clutch",
    "Aishah Sofey",
    "Alice Rosenblum",
    "Ari Kytsya",
    "Kira Pregiato",
    "Madiii Tay",
    "Mikayla Campinos",
    "Sophie Rain",
    "Waifu Mia",
]
MEDIA_EXT = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".heic",
    ".mp4",
    ".mov",
    ".webm",
    ".mkv",
    ".m4v",
    ".avi",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# Build moved-content hash index
print("Indexing content/ hashes...")
moved = set()
for p in CONTENT.rglob("*"):
    if p.is_file() and p.suffix.lower() in MEDIA_EXT:
        moved.add(p.stem[:12])  # filename = hash[:12]
print(f"  {len(moved)} unique files in content/")

# Check every leftover
print("\nChecking leftover source files...")
total = dup = unique = 0
unique_files = []
for person in PERSON_DIRS:
    pdir = ROOT / person
    if not pdir.exists():
        continue
    for p in pdir.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in MEDIA_EXT:
            continue
        total += 1
        h12 = sha(p)[:12]
        if h12 in moved:
            dup += 1
        else:
            unique += 1
            unique_files.append(str(p))
        if total % 1000 == 0:
            print(f"  checked {total}...")

print("\n=== VERIFICATION RESULT ===")
print(f"Total leftover media:     {total}")
print(f"  Dedup copies (safe):    {dup}")
print(f"  UNIQUE missed (BUG):    {unique}")
if unique_files:
    print("\nFirst 20 unique-missed files:")
    for f in unique_files[:20]:
        print(f"  {f}")
