"""Seed a small, deterministic catalog.db + license-clean placeholder media for
Playwright e2e (NEVER the real library).

Usage: python scripts/seed_test_catalog.py <db_path>

Idempotent — recreates the DB from scratch each run. Produces enough shape for
every app surface to render with REAL content: 12 images across 3 people / 4
ratings (with tags) + 3 videos, and a generated placeholder WebP for every image
and video poster so grids, tiles, and the lightbox render actual pixels (not
404'd thumbnails) for the visual audit.

Placeholders are generated locally (distinct-hue gradients) — public-domain, no
network, no real library media. They land under the content root
(``MEDIA_PIPELINE_CONTENT_ROOT``, or ``<db_parent>/content`` as a fallback), NEVER
the real ``content/`` tree. Never touches data/catalog.db.
"""

from __future__ import annotations

import colorsys
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image as PILImage
from PIL import ImageDraw

# Allow running as a bare script (python scripts/seed_test_catalog.py): put the
# repo root — not scripts/ — on sys.path so `pipeline` imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.database import Database, Image, Tag, Video  # noqa: E402

PEOPLE = ("ava", "mia", "zoe")
RATINGS = ("sfw", "suggestive", "nsfw", "unrated")

# (w, h) per image index % 3 — mix portrait / landscape / square so the grid
# looks like a real heterogeneous library rather than a uniform mosaic.
_SIZES = ((1024, 1536), (1536, 1024), (1200, 1200))


def _placeholder(dest: Path, w: int, h: int, label: str, idx: int) -> None:
    """Write a distinct-hue gradient WebP with a small centered label.

    Public-domain generated pixels — safe to ship as a test fixture and to feed
    to any model in the visual audit (no real media, no privacy concern).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    hue = (idx * 0.137) % 1.0  # golden-ish hue step for visually distinct tiles
    top = np.array(colorsys.hls_to_rgb(hue, 0.52, 0.55))
    bot = np.array(colorsys.hls_to_rgb(hue, 0.30, 0.50))
    grad = top + (bot - top) * np.linspace(0.0, 1.0, h)[:, None]  # (h, 3)
    arr = np.repeat(grad[:, None, :], w, axis=1)  # (h, w, 3)
    img = PILImage.fromarray((arr * 255).astype("uint8"), "RGB")
    ImageDraw.Draw(img).text((w // 2, h // 2), label, fill=(255, 255, 255), anchor="mm")
    img.save(dest, "WEBP", quality=82)


def _content_root(db_path: str) -> Path:
    root = os.environ.get("MEDIA_PIPELINE_CONTENT_ROOT")
    return Path(root) if root else Path(db_path).resolve().parent / "content"


def seed(db_path: str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    content_root = _content_root(db_path)

    # Full schema = base ORM tables + every migration (collections, vec, captions
    # FTS, faces, geo, owner_id, …) so the seeded DB matches a real catalog and no
    # endpoint hits a missing table. No backup (throwaway test DB).
    from pipeline.bootstrap import run_pending_migrations

    run_pending_migrations(str(path), do_backup=False)

    db = Database(str(path))
    session = db.get_session()
    try:
        for i in range(12):
            person = PEOPLE[i % len(PEOPLE)]
            rating = RATINGS[i % len(RATINGS)]
            w, h = _SIZES[i % len(_SIZES)]
            rel = f"library/{person}/{rating}/img{i:02d}.webp"
            _placeholder(content_root / rel, w, h, f"{person} {i:02d}", i)
            img = Image(
                path=rel,
                filename=f"img{i:02d}.webp",
                person=person,
                file_hash=f"imghash{i:02d}",
                width=w,
                height=h,
                format="webp",
                processed=True,
                media_type="image",
            )
            session.add(img)
            session.flush()  # assign img.id for the tag FKs
            session.add_all(
                [
                    Tag(
                        image_id=img.id,
                        category="content_type",
                        value="portrait",
                        confidence=0.9,
                        tag_source="seed",
                    ),
                    Tag(
                        image_id=img.id,
                        category="setting",
                        value="outdoor" if i % 2 else "studio",
                        confidence=0.8,
                        tag_source="seed",
                    ),
                ]
            )

        for i in range(3):
            person = PEOPLE[i % len(PEOPLE)]
            poster_rel = f"library/{person}/videos/clip{i:02d}_poster.webp"
            _placeholder(
                content_root / poster_rel, 1280, 720, f"{person} clip {i:02d}", i + 5
            )
            session.add(
                Video(
                    path=f"library/{person}/videos/clip{i:02d}.mp4",
                    filename=f"clip{i:02d}.mp4",
                    person=person,
                    file_hash=f"vidhash{i:02d}",
                    duration=30.0 + i * 45,
                    width=1920,
                    height=1080,
                    fps=30.0,
                    has_audio=1,
                    poster_path=poster_rel,
                    rating="sfw",
                    processed=1,
                    media_type="video",
                )
            )

        session.commit()
    finally:
        session.close()

    print(f"seeded {db_path}: 12 images + 3 videos, placeholders under {content_root}")


if __name__ == "__main__":
    seed(sys.argv[1] if len(sys.argv) > 1 else "data/e2e_catalog.db")
