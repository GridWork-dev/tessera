#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""
Format normalize: transcode the mixed image corpus to canonical WebP Q=90.

Companion to normalize_relocate.py (which unified filenames + layout + dedup
but preserved original extensions). This closes the format gap. See
docs/research/format-normalization-2026.md for the decision.

Single-pass: the worker is mode-aware.
  - Dry-run: encode to buffer, project savings, write nothing.
  - Execute: encode to buffer, write the .webp, and unlink the original IN THE
    SAME pass (no redundant re-encode).

Per file:
  - skip non-convertible (.webp already done; .gif often animated — left alone)
  - pyvips encode WebP Q=90, strip metadata, no resize
  - new filename <sha256(webp_bytes)[:12]>.webp — preserves the
    filename_stem == content_hash[:12] invariant from the destructive normalize
  - default SIZE GUARD: keep the webp only if strictly smaller than the source,
    else leave the original in place (action=kept-original)
  - --force: bypass the size guard for a uniform WebP corpus
  - idempotent: if <stem>.webp already exists (prior partial run), just unlink src

Collision behavior (post-pass, report-only): webp hash[:12] collisions can occur
when byte-distinct sources decode to identical pixels and encode to identical
webp bytes. The existing .webp is retained and the source duplicate is unlinked;
this intentionally collapses pixel-identical near-duplicates, and logs the count.

Usage:
  python scripts/normalize_format.py                      # dry-run projection
  python scripts/normalize_format.py --execute            # transcode if smaller
  python scripts/normalize_format.py --execute --force    # uniform WebP corpus
  python scripts/normalize_format.py --execute --workers 8
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

# pyvips encodes (Pillow in this venv can't write webp); PIL decodes downstream.
import pyvips

REPO = Path(__file__).resolve().parent.parent
LIBRARY = REPO / "content" / "library"

# Convert these to webp. (.webp is already optimal; .gif may be animated.)
CONVERTIBLE = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
SKIP = {".webp", ".gif"}

DEFAULT_QUALITY = 90
_DESCRIPTION = __doc__ or ""


@dataclass
class FilePlan:
    src: str
    src_ext: str
    src_size: int
    new_stem: str | None  # <hash[:12]> of the webp bytes, or None if not converted
    new_size: int  # webp byte length (0 if not encoded)
    action: str  # convert | skip-webp | skip-gif | kept-original | error
    note: str = ""


def _process_one(args: tuple[str, int, bool, bool]) -> FilePlan:
    """Mode-aware worker. Encodes once; writes+unlinks only when execute=True.

    Returns a FilePlan describing the outcome (used for the summary in both
    modes, and reflects actual on-disk state in execute mode)."""
    src_str, quality, execute, force = args
    p = Path(src_str)
    ext = p.suffix.lower()
    try:
        src_size = p.stat().st_size
    except OSError as e:
        return FilePlan(src_str, ext, 0, None, 0, "error", f"stat: {e}")

    if ext in SKIP:
        return FilePlan(src_str, ext, src_size, None, 0, f"skip-{ext.lstrip('.')}")
    if ext not in CONVERTIBLE:
        return FilePlan(src_str, ext, src_size, None, 0, "skip-unknown")

    # Encode once. pyvips' dynamic return type is wider than the concrete Image
    # object at runtime, so cast away stub noise before calling webpsave_buffer.
    try:
        im = cast(Any, pyvips.Image.new_from_file(src_str, access="sequential"))
        buf = im.webpsave_buffer(Q=quality, strip=True)
    except Exception as e:  # corrupt / unreadable
        return FilePlan(
            src_str, ext, src_size, None, 0, "error", f"{type(e).__name__}: {e}"
        )

    webp_size = len(buf)
    if webp_size >= src_size and not force:
        # No win — leave the original in place.
        return FilePlan(
            src_str,
            ext,
            src_size,
            None,
            webp_size,
            "kept-original",
            f"webp {webp_size}B >= src {src_size}B",
        )

    new_stem = hashlib.sha256(buf).hexdigest()[:12]
    dst = p.with_name(f"{new_stem}.webp")

    if execute:
        try:
            # Write the buffer we already hold directly to disk. Do NOT re-encode
            # via pyvips: the image was opened with access="sequential", whose
            # stream is consumed by the webpsave_buffer call above — a second
            # read raises "VipsJpeg: out of order read". The buffer IS the webp
            # file, so write_bytes produces an identical result, one encode only.
            # Idempotent: a prior partial run may have left the .webp in place.
            if not dst.exists():
                dst.write_bytes(buf)
            # Unlink the original only after the webp lands (dst != src always,
            # since extensions differ for convertible inputs).
            if dst.resolve() != p.resolve():
                p.unlink()
        except Exception as e:
            return FilePlan(
                src_str,
                ext,
                src_size,
                new_stem,
                webp_size,
                "error",
                f"write/unlink: {type(e).__name__}: {e}",
            )

    return FilePlan(src_str, ext, src_size, new_stem, webp_size, "convert")


def scan_library(library: Path) -> list[Path]:
    out = []
    for p in library.rglob("*"):
        if (
            p.is_file()
            and not p.name.startswith(".")
            and p.suffix.lower() in (CONVERTIBLE | SKIP)
        ):
            out.append(p)
    return out


def process_all(
    files: list[Path], workers: int, quality: int, execute: bool, force: bool
) -> list[FilePlan]:
    """Run the pool. Each file is encoded exactly once."""
    plans: list[FilePlan] = []
    jobs = [(str(f), quality, execute, force) for f in files]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_process_one, job): job for job in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            plans.append(fut.result())
            if i % 1000 == 0:
                print(f"  processed {i}/{len(files)}...", flush=True)
    return plans


def detect_collisions(plans: list[FilePlan]) -> list[str]:
    """Report any hash[:12] stem collisions among converts (expected: none)."""
    by_stem: dict[str, int] = {}
    for p in plans:
        if p.action == "convert" and p.new_stem:
            by_stem[p.new_stem] = by_stem.get(p.new_stem, 0) + 1
    return [stem for stem, n in by_stem.items() if n > 1]


def summarize(plans: list[FilePlan], execute: bool) -> None:
    by_action = Counter(p.action for p in plans)
    by_src_ext = Counter(p.src_ext for p in plans if p.action == "convert")

    convert = [p for p in plans if p.action == "convert"]
    kept = [p for p in plans if p.action == "kept-original"]
    errors = [p for p in plans if p.action == "error"]
    skips = [p for p in plans if p.action.startswith("skip")]

    src_bytes = sum(p.src_size for p in convert)
    webp_bytes = sum(p.new_size for p in convert)
    saved = src_bytes - webp_bytes
    pct = (saved / src_bytes * 100) if src_bytes else 0.0

    print("=" * 64)
    print("FORMAT NORMALIZE — " + ("EXECUTE" if execute else "DRY RUN") + " SUMMARY")
    print("=" * 64)
    print(f"Total files scanned:      {len(plans):>8}")
    for act, n in by_action.most_common():
        print(f"  {act:<14}          {n:>8}")
    print()
    if convert:
        print(f"Convert: {len(convert)} files")
        print(f"  source bytes:   {src_bytes:>14,}  ({src_bytes / 1073741824:.2f} GB)")
        print(
            f"  webp q90 bytes: {webp_bytes:>14,}  ({webp_bytes / 1073741824:.2f} GB)"
        )
        print(
            f"  SAVED:          {saved:>14,}  ({saved / 1073741824:.2f} GB, {pct:.1f}%)"
        )
        print("  by source format:")
        for ext, n in by_src_ext.most_common():
            sub = [p for p in convert if p.src_ext == ext]
            sb = sum(p.src_size for p in sub)
            wb = sum(p.new_size for p in sub)
            sp = (sb - wb) / sb * 100 if sb else 0
            print(
                f"    {ext:<6} {n:>6} files  "
                f"{sb / 1073741824:>6.2f}GB -> {wb / 1073741824:>6.2f}GB  (-{sp:.1f}%)"
            )
    if kept:
        print(f"\nKept-original (webp not smaller): {len(kept)}")
    if skips:
        print(f"\nSkipped: {len(skips)} (already webp / gif / unknown)")
    if errors:
        print(f"\nERRORS: {len(errors)}")
        for p in errors[:20]:
            print(f"  {Path(p.src).name}: {p.note}")

    print()
    print("Sample conversions (first 6):")
    for p in convert[:6]:
        delta = p.src_size - p.new_size
        print(
            f"  {Path(p.src).name[:28]:<28} {p.src_size:>9}B -> "
            f"{p.new_size:>9}B  (-{delta / p.src_size * 100:.1f}%)"
        )
    print("=" * 64)


def main() -> int:
    ap = argparse.ArgumentParser(description=_DESCRIPTION.split("\n\n")[0])
    ap.add_argument("--library", default=str(LIBRARY), help="library root")
    ap.add_argument(
        "--execute",
        action="store_true",
        help="write webp + unlink originals (single pass)",
    )
    ap.add_argument("--workers", type=int, default=4, help="parallel encode workers")
    ap.add_argument(
        "--quality", type=int, default=DEFAULT_QUALITY, help="webp quality (default 90)"
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="force-convert even when webp would be larger than the source "
        "(for a uniform corpus; still skips .webp/.gif and un-convertible)",
    )
    args = ap.parse_args()

    library = Path(args.library)
    if not library.is_dir():
        print(f"ERROR: library not found: {library}", file=sys.stderr)
        return 1

    print(f"Scanning {library}...", flush=True)
    files = scan_library(library)
    print(
        f"Found {len(files)} candidate files. "
        f"{'EXECUTE' if args.execute else 'DRY-RUN'}"
        f"{' --force' if args.force else ''} "
        f"(Q={args.quality}, {args.workers} workers, single-pass)...\n",
        flush=True,
    )

    t0 = time.time()
    plans = process_all(files, args.workers, args.quality, args.execute, args.force)

    collisions = detect_collisions(plans)
    if collisions:
        print(
            f"\nWARNING: {len(collisions)} hash[:12] stem collision(s): {collisions[:5]}\n"
            "  (near-duplicate content collapsed via last-write-wins; audit if unexpected.)",
            flush=True,
        )

    summarize(plans, args.execute)
    print(f"Total time: {time.time() - t0:.1f}s\n", flush=True)

    if not args.execute:
        print(
            "DRY RUN ONLY. Re-run with --execute to transcode in place (single pass)."
        )
        return 0

    # Execute: reflect actual on-disk result.
    written = sum(1 for p in plans if p.action == "convert")
    errors = [p for p in plans if p.action == "error"]
    print(
        f"Execute complete: {written} webp written (+ originals unlinked), "
        f"{len([p for p in plans if p.action == 'kept-original'])} kept-original, "
        f"{len([p for p in plans if p.action.startswith('skip')])} skipped."
    )
    if errors:
        print(f"ERRORS ({len(errors)}) — originals for these were NOT unlinked:")
        for p in errors[:20]:
            print(f"  {Path(p.src).name}: {p.note}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
