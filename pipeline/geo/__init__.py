"""Geo lane — GPS extraction, offline reverse-geocoding, events, scene tags.

Local-first and dependency-light: importing this package pulls in NO heavy or
optional deps (``exiftool`` / ``reverse_geocoder`` / torch are all imported
lazily inside the function that needs them). Only the pure helpers are
re-exported here so callers and tests get a stable surface.
"""

from __future__ import annotations

from pipeline.geo.events import Event, cluster_events, haversine_km
from pipeline.geo.gps import dms_to_decimal, parse_exif_gps
from pipeline.geo.reverse_geocode import normalize_result, place_key
from pipeline.geo.scene_tags import (
    SCENE_LABELS,
    SCENE_VOCAB,
    score_scene_tags,
)

__all__ = [
    "Event",
    "cluster_events",
    "haversine_km",
    "dms_to_decimal",
    "parse_exif_gps",
    "normalize_result",
    "place_key",
    "SCENE_LABELS",
    "SCENE_VOCAB",
    "score_scene_tags",
]
