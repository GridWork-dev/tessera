"""Wave 2c Task A — ingest path placement is decoupled from rating.

New ingest no longer routes by rating: the default image bucket is ``_unsorted``
and ``build_rel_path`` no longer requires a ``rating`` argument. Already-placed
``library/<person>/<rating>/...`` paths remain opaque strings that still resolve.
No torch / no network; nothing touches data/catalog.db.
"""

from __future__ import annotations

from pathlib import Path

from pipeline.paths import build_rel_path, resolve_image_path


def test_new_image_placement_defaults_to_unsorted():
    # No rating argument required: a new image lands in the generic bucket.
    rel = build_rel_path("ava", "deadbeef0001.webp")
    assert rel == "library/ava/_unsorted/deadbeef0001.webp"


def test_unsorted_person_routes_to_top_unsorted():
    rel = build_rel_path("_unsorted", "deadbeef0002.webp")
    assert rel == "_unsorted/_unsorted/_unsorted/deadbeef0002.webp"


def test_video_still_routes_to_videos_bucket():
    rel = build_rel_path("ava", "clip0001.mp4", media_type="video")
    assert rel == "library/ava/videos/clip0001.mp4"


def test_existing_rated_path_resolves_unchanged():
    # An already-placed rated relative path is an opaque string and still
    # resolves to <content_root>/<that exact path>.
    rel = "library/ava/nsfw/abc123abc123.webp"
    resolved = resolve_image_path(rel)
    assert resolved.parts[-3:] == ("ava", "nsfw", "abc123abc123.webp")
    assert isinstance(resolved, Path)
