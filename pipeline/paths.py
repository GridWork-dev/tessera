"""
Path resolution for the normalized content layout.

Single source of truth for translating between relative DB paths and absolute
filesystem paths. The destructive-normalize move stores every Image.path as a
path RELATIVE to the content root:

    library/<person_slug>/_unsorted/<hash[:12]>.<ext>   (NEW images)
    library/<person_slug>/videos/<hash[:12]>.<ext>
    library/<person_slug>/<rating>/<hash[:12]>.<ext>    (LEGACY, opaque — not rewritten)

All consumers (webui, grid, embedder, ingest) MUST go through resolve_image_path()
so the content root can move without touching the DB.

Placement is decoupled from rating (Wave 2c): rating is a removable label set,
not a directory level. New images land in ``_unsorted``; legacy rated paths stay
as opaque strings (already-placed files are never moved).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pipeline.settings import settings

# Repo root + content root now flow from the typed settings layer (Spec A), so a
# config.yaml / MEDIA_PIPELINE_* override moves them without editing this module.
# Defaults reproduce the historical __file__-derived layout (REPO_ROOT/content).
REPO_ROOT = settings.project_root
CONTENT_ROOT = settings.content_root

VALID_RATINGS = ("unrated", "sfw", "suggestive", "nsfw")
MEDIA_TYPES = ("image", "video")


@lru_cache(maxsize=1)
def content_root() -> Path:
    """Absolute content root. Cached; call clear_resolver_cache() after moves."""
    return settings.content_root


def clear_resolver_cache() -> None:
    content_root.cache_clear()


def resolve_image_path(rel_path: str) -> Path:
    """Relative DB path -> absolute filesystem path.

    Accepts both new-style relative ('library/.../x.jpg') and legacy absolute
    ('/Users/.../x.jpg') for the transition window. Absolute paths pass through
    unchanged so pre-move rows still resolve.
    """
    p = Path(rel_path)
    if p.is_absolute():
        return p
    return content_root() / p


def relative_to_content(abs_path: Path | str) -> str:
    """Absolute filesystem path -> relative DB path string.

    Raises ValueError if the path is not under the content root. Used by ingest
    on the write side so every stored path is portable.
    """
    p = Path(abs_path).resolve()
    try:
        rel = p.relative_to(content_root().resolve())
    except ValueError as exc:
        raise ValueError(
            f"Path {p} is not under content root {content_root()}"
        ) from exc
    return str(rel)


def build_rel_path(person_slug: str, filename: str, media_type: str = "image") -> str:
    """Compose a relative DB path for a NEW file in the normalized layout.

    Placement is decoupled from rating (Wave 2c): rating is now a removable
    label set, not a directory level, so new images land in the generic
    ``_unsorted`` bucket and videos in ``videos``. Already-placed
    ``library/<person>/<rating>/...`` paths are NOT rewritten — they stay
    opaque strings and still resolve via resolve_image_path().

    person_slug: '_unsorted' routes to the top-level generic bucket.
    """
    bucket = "videos" if media_type == "video" else "_unsorted"
    top = "_unsorted" if person_slug == "_unsorted" else "library"
    return f"{top}/{person_slug}/{bucket}/{filename}"
