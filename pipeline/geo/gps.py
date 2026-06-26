"""GPS extraction from stills + video via ExifTool (PyExifTool).

ExifTool is the single extractor that reads GPS out of JPEG/HEIC EXIF *and*
MP4/MOV/QuickTime containers. The heavy ``exiftool`` dependency (the Python
wrapper + the system binary) is imported lazily inside ``extract_gps`` so this
module imports cleanly on a box that lacks it and the pure helpers below stay
testable with no dependency.

Privacy: ExifTool reads the GPS that the file *already carries* — nothing leaves
the box. Paths are resolved by the caller via ``pipeline/paths.py``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ExifTool tag names we read, in preference order. The Composite tags are
# already-signed decimals; the raw EXIF tags need the *Ref to sign them; the
# QuickTime/video tag is an ISO6709 "+lat+lon" string.
_LAT_DECIMAL = ("Composite:GPSLatitude", "EXIF:GPSLatitude", "GPSLatitude")
_LON_DECIMAL = ("Composite:GPSLongitude", "EXIF:GPSLongitude", "GPSLongitude")
_LAT_REF = ("EXIF:GPSLatitudeRef", "GPSLatitudeRef")
_LON_REF = ("EXIF:GPSLongitudeRef", "GPSLongitudeRef")
_VIDEO_COORDS = (
    "Composite:GPSCoordinates",
    "QuickTime:GPSCoordinates",
    "GPSCoordinates",
)


def dms_to_decimal(
    deg: float, minute: float, sec: float, ref: str | None
) -> float | None:
    """Degrees/minutes/seconds + a N/S/E/W ref -> signed decimal degrees.

    Returns ``None`` when the inputs are non-numeric or the result falls outside
    the valid lat/lon envelope (a corrupt-EXIF guard).
    """
    try:
        decimal = float(deg) + float(minute) / 60.0 + float(sec) / 3600.0
    except TypeError, ValueError:
        return None
    if ref and str(ref).strip().upper()[:1] in ("S", "W"):
        decimal = -decimal
    if not -180.0 <= decimal <= 180.0:
        return None
    return decimal


def _first(tags: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in tags and tags[k] not in (None, ""):
            return tags[k]
    return None


def _signed(value: Any, ref: Any) -> float | None:
    """A decimal-degree value (already ``float``-able) signed by its ref."""
    try:
        decimal = float(value)
    except TypeError, ValueError:
        return None
    if ref and str(ref).strip().upper()[:1] in ("S", "W"):
        decimal = -abs(decimal)
    return decimal


def parse_exif_gps(tags: dict[str, Any]) -> tuple[float, float] | None:
    """Map an ExifTool tag dict to ``(lat, lon)`` decimal degrees, or ``None``.

    Tolerates the three shapes ExifTool emits:
      1. Composite/EXIF decimal lat/lon (+ optional *Ref to sign them),
      2. a QuickTime/video ``GPSCoordinates`` ISO6709 "+lat+lon[+alt]" string,
      3. missing GPS -> ``None``.
    """
    if not tags:
        return None

    # 1. Decimal lat/lon (stills, and Composite video tags).
    lat_v = _first(tags, _LAT_DECIMAL)
    lon_v = _first(tags, _LON_DECIMAL)
    if lat_v is not None and lon_v is not None:
        lat = _signed(lat_v, _first(tags, _LAT_REF))
        lon = _signed(lon_v, _first(tags, _LON_REF))
        if lat is not None and lon is not None and _valid(lat, lon):
            return (lat, lon)

    # 2. Video container coordinate string, e.g. "+37.7749-122.4194/".
    coords = _first(tags, _VIDEO_COORDS)
    parsed = _parse_iso6709(coords) if coords is not None else None
    if parsed is not None:
        return parsed

    return None


def _valid(lat: float, lon: float) -> bool:
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def _parse_iso6709(s: Any) -> tuple[float, float] | None:
    """Parse an ISO 6709 "+DD.dddd-DDD.dddd[+alt]/" string -> ``(lat, lon)``."""
    text = str(s).strip().rstrip("/")
    if not text:
        return None
    # Split on the sign that starts the longitude (the 2nd +/- in the string).
    nums: list[str] = []
    cur = ""
    for ch in text:
        if ch in "+-" and cur:
            nums.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        nums.append(cur)
    if len(nums) < 2:
        return None
    try:
        lat, lon = float(nums[0]), float(nums[1])
    except ValueError:
        return None
    return (lat, lon) if _valid(lat, lon) else None


def extract_gps(paths: list[Path | str]) -> dict[str, tuple[float, float]]:
    """Batch-extract GPS for ``paths`` -> ``{path_str: (lat, lon)}``.

    Files with no GPS are simply absent from the returned map. Requires the
    ``pyexiftool`` package and the ``exiftool`` binary (lazy import — callers in
    a model-free environment should not reach this function). Read-only.
    """
    if not paths:
        return {}
    import exiftool  # lazy: pyexiftool + the system `exiftool` binary

    str_paths = [str(p) for p in paths]
    out: dict[str, tuple[float, float]] = {}
    with exiftool.ExifToolHelper() as et:
        for path, meta in zip(str_paths, et.get_metadata(str_paths)):
            coords = parse_exif_gps(meta)
            if coords is not None:
                out[path] = coords
    return out
