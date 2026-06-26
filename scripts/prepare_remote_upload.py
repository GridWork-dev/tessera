#!/usr/bin/env python3
"""
H100 OFFLOAD — LOCAL-ONLY upload preparer (runs on the Mac, never the box).

Selects images from catalog.db, copies them into a flat staging dir renamed to
``<image_id>.webp`` (id = the catalog.db integer primary key, the ONLY identifier
the box ever sees), writes a LOCAL-ONLY manifest mapping each id back to its
original path / person / rating, then tars + ENCRYPTS the staging dir and writes
checksums.

PRIVACY CONTRACT (this is the whole point of the script)
--------------------------------------------------------
What the box receives (the encrypted tarball, after you decrypt it on-box):
  * ONLY ``<int>.webp`` flat files. No real filenames, no directory structure,
    no person/rating taxonomy, no catalog.db.
What stays on the Mac and NEVER leaves it:
  * ``manifest.json`` — id -> {original_path, person, rating, file_hash}. This is
    the key that maps results back; losing it makes the artifacts useless, so it
    is written OUTSIDE the staging dir and is NEVER tarred/uploaded.
  * The decryption identity/passphrase.

Encryption at rest: the tarball is encrypted with ``age`` (preferred) or ``gpg``
so plaintext never sits on the box's disk until you decrypt it (ideally into a
tmpfs/ramdisk on-box). SHA-256 checksums are emitted for transfer integrity.

Usage (examples)
----------------
  # All images, age symmetric (passphrase) encryption:
  python3 scripts/prepare_remote_upload.py --all --encrypt age

  # A 500-image pilot (lowest ids), age recipient (public key) encryption:
  python3 scripts/prepare_remote_upload.py --limit 500 \
      --encrypt age --age-recipient age1qz...   # your public key

  # Scope to specific ids (e.g. a parity re-check set):
  python3 scripts/prepare_remote_upload.py --ids 12,34,56 --encrypt gpg \
      --gpg-recipient you@example.com

  # Scope by person/rating (the taxonomy is used HERE on the Mac to SELECT, but
  # is never written into any uploaded file):
  python3 scripts/prepare_remote_upload.py --person alice --rating nsfw --all \
      --encrypt age

Outputs (under --work-dir, default outputs/h100/<stamp>/):
  staging/<id>.webp        the flat upload payload (pre-tar)
  upload.tar               tar of staging/ (deleted after encryption unless --keep-tar)
  upload.tar.age | .gpg    ENCRYPTED tarball -> this is what you upload
  manifest.json            LOCAL-ONLY id->meta map (DO NOT UPLOAD)
  checksums.sha256         sha256 of the encrypted tarball (+ tar if kept)
  prepare_summary.json     counts + paths + which ids were staged

This script does NOT connect anywhere. The rental/transfer happens later, by
hand, per docs/runbooks/h100-vastai.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "catalog.db"
CONTENT_ROOT = REPO_ROOT / "content"


def resolve_image_path(rel_path: str) -> Path:
    """Relative DB path -> absolute (mirrors pipeline/paths.resolve_image_path)."""
    p = Path(rel_path)
    if p.is_absolute():
        return p
    return CONTENT_ROOT / p


def select_rows(
    conn: sqlite3.Connection,
    *,
    take_all: bool,
    limit: int | None,
    ids: list[int] | None,
    person: str | None,
    rating: str | None,
) -> list[tuple[int, str, str | None, str | None, str | None]]:
    """Return (id, path, person, rating, file_hash) rows for the selection.

    media_type is constrained to 'image' so the video corpus never ships.
    Rating is the Rating LABEL set now (Wave 2c — images.rating column dropped):
    sourced via a LEFT JOIN on user_labels / label_sets.
    """
    sql = (
        "SELECT i.id, i.path, i.person, rl.value, i.file_hash FROM images i "
        "LEFT JOIN ("
        "  SELECT ul.image_id, ul.value FROM user_labels ul "
        "  JOIN label_sets ls ON ul.set_id = ls.id WHERE ls.name = 'Rating'"
        ") rl ON rl.image_id = i.id "
        "WHERE i.media_type = 'image'"
    )
    params: list[Any] = []
    if ids:
        placeholders = ",".join("?" for _ in ids)
        sql += f" AND i.id IN ({placeholders})"
        params.extend(ids)
    if person:
        sql += " AND i.person = ?"
        params.append(person)
    if rating:
        sql += " AND rl.value = ?"
        params.append(rating)
    sql += " ORDER BY i.id"
    if limit is not None and not take_all:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stage_images(
    rows: list[tuple[int, str, str | None, str | None, str | None]],
    staging: Path,
) -> tuple[dict[str, dict[str, Any]], list[int]]:
    """Copy each image to staging/<id>.webp. Return (manifest, staged_ids).

    The manifest is keyed by str(id) (JSON object keys are strings) and holds the
    private mapping. The on-disk staged file carries ONLY the id in its name.
    """
    staging.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict[str, Any]] = {}
    staged_ids: list[int] = []
    missing = 0
    for img_id, rel_path, person, rating, file_hash in rows:
        src = resolve_image_path(rel_path)
        if not src.exists():
            print(
                f"  ! missing on disk, skipping id={img_id}: {rel_path}",
                file=sys.stderr,
            )
            missing += 1
            continue
        # Flat, taxonomy-free destination: ONLY the integer id.
        dst = staging / f"{img_id}.webp"
        shutil.copy2(src, dst)
        manifest[str(img_id)] = {
            "original_path": rel_path,  # relative DB path — LOCAL ONLY
            "person": person,
            "rating": rating,
            "file_hash": file_hash,
        }
        staged_ids.append(img_id)
    if missing:
        print(f"  ({missing} rows skipped: file not found on disk)", file=sys.stderr)
    return manifest, staged_ids


def make_tar(staging: Path, tar_path: Path) -> None:
    """Tar the staging dir with a flat arcname (no host paths leak into the tar)."""
    with tarfile.open(tar_path, "w") as tar:
        for p in sorted(staging.iterdir()):
            if p.is_file():
                tar.add(p, arcname=p.name)  # arcname = '<id>.webp' only


def encrypt_age(tar_path: Path, recipient: str | None) -> Path:
    """Encrypt with age. recipient=None -> symmetric (-p, passphrase prompt)."""
    out = tar_path.with_suffix(tar_path.suffix + ".age")
    cmd = ["age", "-o", str(out)]
    if recipient:
        cmd += ["-r", recipient]
    else:
        cmd += ["-p"]  # interactive passphrase
    cmd += [str(tar_path)]
    subprocess.run(cmd, check=True)
    return out


def encrypt_gpg(tar_path: Path, recipient: str | None) -> Path:
    """Encrypt with gpg. recipient=None -> symmetric (-c, passphrase prompt)."""
    out = tar_path.with_suffix(tar_path.suffix + ".gpg")
    if recipient:
        cmd = ["gpg", "--yes", "-o", str(out), "-e", "-r", recipient, str(tar_path)]
    else:
        cmd = ["gpg", "--yes", "-o", str(out), "-c", str(tar_path)]
    subprocess.run(cmd, check=True)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Stage + encrypt a privacy-safe H100 upload"
    )
    ap.add_argument("--db", default=str(DEFAULT_DB), help="Path to catalog.db")
    ap.add_argument(
        "--work-dir",
        default=None,
        help="Output dir (default outputs/h100/<timestamp>/)",
    )
    sel = ap.add_argument_group("selection")
    sel.add_argument("--all", action="store_true", help="Select all images")
    sel.add_argument("--limit", type=int, default=None, help="Cap selection (pilot)")
    sel.add_argument("--ids", default=None, help="Comma list of explicit image ids")
    sel.add_argument(
        "--person", default=None, help="Scope to one person (local-only filter)"
    )
    sel.add_argument("--rating", default=None, help="Scope to one rating bucket")
    enc = ap.add_argument_group("encryption")
    enc.add_argument(
        "--encrypt",
        choices=["age", "gpg", "none"],
        default="age",
        help="Encrypt the tarball at rest (default age)",
    )
    enc.add_argument(
        "--age-recipient", default=None, help="age public key (else passphrase)"
    )
    enc.add_argument(
        "--gpg-recipient", default=None, help="gpg recipient (else passphrase)"
    )
    ap.add_argument(
        "--keep-tar",
        action="store_true",
        help="Keep the plaintext .tar after encryption (default: delete)",
    )
    args = ap.parse_args(argv)

    if not (args.all or args.limit or args.ids):
        ap.error("select something: --all, --limit N, or --ids a,b,c")

    ids = [int(x) for x in args.ids.split(",") if x.strip()] if args.ids else None

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    work_dir = (
        Path(args.work_dir)
        if args.work_dir
        else (REPO_ROOT / "outputs" / "h100" / stamp)
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    staging = work_dir / "staging"

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"catalog.db not found at {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(db_path))
    try:
        rows = select_rows(
            conn,
            take_all=args.all,
            limit=args.limit,
            ids=ids,
            person=args.person,
            rating=args.rating,
        )
    finally:
        conn.close()

    if not rows:
        print("no images matched the selection", file=sys.stderr)
        return 1
    print(f"selected {len(rows)} images; staging to {staging} ...")

    manifest, staged_ids = stage_images(rows, staging)
    if not staged_ids:
        print("nothing staged (all missing on disk)", file=sys.stderr)
        return 1

    # Manifest goes to work_dir, OUTSIDE staging — it is never tarred/uploaded.
    manifest_path = work_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"  wrote LOCAL-ONLY manifest ({len(manifest)} ids) -> {manifest_path}")
    print("  *** manifest.json must NEVER leave the Mac ***")

    tar_path = work_dir / "upload.tar"
    print(f"  taring {len(staged_ids)} files (flat <id>.webp arcnames) ...")
    make_tar(staging, tar_path)

    checksums: dict[str, str] = {}
    final_upload: Path
    if args.encrypt == "age":
        final_upload = encrypt_age(tar_path, args.age_recipient)
    elif args.encrypt == "gpg":
        final_upload = encrypt_gpg(tar_path, args.gpg_recipient)
    else:
        final_upload = tar_path  # plaintext — discouraged; the runbook uses age
        print(
            "  WARNING: --encrypt none -> plaintext tar will be uploaded.",
            file=sys.stderr,
        )

    checksums[final_upload.name] = sha256_file(final_upload)
    if args.keep_tar or args.encrypt == "none":
        checksums[tar_path.name] = sha256_file(tar_path)
    if args.encrypt != "none" and not args.keep_tar:
        tar_path.unlink(missing_ok=True)  # don't leave plaintext lying around

    checksums_path = work_dir / "checksums.sha256"
    checksums_path.write_text(
        "".join(f"{digest}  {name}\n" for name, digest in checksums.items())
    )

    summary = {
        "timestamp": stamp,
        "db": str(db_path),
        "selected": len(rows),
        "staged": len(staged_ids),
        "staged_ids_min": min(staged_ids),
        "staged_ids_max": max(staged_ids),
        "encrypt": args.encrypt,
        "upload_file": str(final_upload),
        "upload_sha256": checksums.get(final_upload.name),
        "manifest_local_only": str(manifest_path),
        "staging_dir": str(staging),
    }
    (work_dir / "prepare_summary.json").write_text(json.dumps(summary, indent=2))

    print("\n=== READY ===")
    print(f"  UPLOAD THIS    : {final_upload}  ({sha256_file(final_upload)[:16]}...)")
    print(f"  KEEP LOCAL     : {manifest_path}  (id->person/rating/path)")
    print(f"  checksums      : {checksums_path}")
    print(f"  summary        : {work_dir / 'prepare_summary.json'}")
    print("\nNext: upload the encrypted tarball per docs/runbooks/h100-vastai.md.")
    print(
        "After the run, decrypt + import with scripts/import_h100_artifacts.py "
        f"using --manifest {manifest_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
