"""Offline reverse-geocoding: ``(lat, lon)`` -> place name.

Uses the ``reverse_geocoder`` package (a local GeoNames k-d tree) — NO online
geocoder, no network. The package is imported lazily inside ``lookup`` so this
module imports cleanly without it and the pure helpers stay testable.

Self-hosted Nominatim street-level geocoding is a later, optional paid upgrade
(out of scope here, per the master spec).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Grid precision for the dedupe key: 3 decimal places ~= 110 m. Two photos taken
# within ~one block share a single ``places`` row.
_KEY_PRECISION = 3


def place_key(lat: float, lon: float) -> str:
    """A stable dedupe key for a coordinate, rounded to the place grid.

    ``places.place_key`` is UNIQUE on this, so repeated lookups at the same spot
    collapse to one row instead of one place per photo.
    """
    return f"{round(float(lat), _KEY_PRECISION)},{round(float(lon), _KEY_PRECISION)}"


def normalize_result(row: dict[str, Any]) -> dict[str, Any]:
    """A ``reverse_geocoder`` result dict -> the ``places`` column dict.

    ``reverse_geocoder`` returns ``{lat, lon, name, admin1, admin2, cc}``;
    map it to our columns and keep the (float) coordinates it resolved to.
    """
    return {
        "name": row.get("name") or "",
        "admin1": row.get("admin1") or "",
        "admin2": row.get("admin2") or "",
        "cc": row.get("cc") or "",
        "lat": _as_float(row.get("lat")),
        "lon": _as_float(row.get("lon")),
    }


def _as_float(v: Any) -> float | None:
    try:
        return float(v)
    except TypeError, ValueError:
        return None


def lookup(coords: list[tuple[float, float]]) -> list[dict[str, Any]]:
    """Reverse-geocode a batch of ``(lat, lon)`` -> normalized place dicts.

    Output is aligned 1:1 with ``coords``. Requires the ``reverse_geocoder``
    package (lazy import). Fully offline.
    """
    if not coords:
        return []
    import reverse_geocoder as rg  # lazy: bundled GeoNames k-d tree

    results = rg.search([(float(lat), float(lon)) for lat, lon in coords])
    return [normalize_result(r) for r in results]
