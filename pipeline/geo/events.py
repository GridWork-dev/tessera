"""Self-written event / auto-album clustering.

Two stages, reimplemented from first principles (numpy/stdlib only — NO sklearn,
NO copied GPL "journeys" code):

  1. **Time-gap segmentation** — items sorted by timestamp are cut into segments
     wherever the gap to the previous item exceeds ``time_gap_s`` (default 6 h).
     This is the "a new burst of activity = a new event" heuristic.
  2. **GPS-DBSCAN within a segment** — items in one time segment that ALSO carry
     GPS are clustered by a small hand-rolled DBSCAN over haversine distance
     (``gps_eps_km`` / ``min_samples``), so one travel-day splits into the
     distinct places visited. Items without GPS, and DBSCAN noise points, fold
     into the segment's largest cluster (no orphan one-photo "events").

Pure: every function here is deterministic and dependency-light.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# Defaults (overridable by config / caller).
DEFAULT_TIME_GAP_S = 6 * 3600  # 6 hours
DEFAULT_GPS_EPS_KM = 2.0
DEFAULT_MIN_SAMPLES = 2

_EARTH_RADIUS_KM = 6371.0088


@dataclass
class Event:
    """One clustered auto-album."""

    member_ids: list[int] = field(default_factory=list)
    start: float | None = None  # min timestamp (epoch seconds)
    end: float | None = None  # max timestamp
    centroid_lat: float | None = None  # mean GPS of members with coords
    centroid_lon: float | None = None


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in km between two ``(lat, lon)`` points."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def _segment_by_time(items: list[dict[str, Any]], time_gap_s: float) -> list[list[int]]:
    """Sort by timestamp; cut a new segment on each gap > ``time_gap_s``.

    Returns lists of indices into ``items``. Items with no timestamp sort last
    and form their own trailing segment.
    """
    order = sorted(
        range(len(items)),
        key=lambda i: (
            items[i].get("timestamp") is None,
            items[i].get("timestamp") or 0.0,
        ),
    )
    segments: list[list[int]] = []
    cur: list[int] = []
    prev_ts: float | None = None
    for i in order:
        ts = items[i].get("timestamp")
        if (
            cur
            and prev_ts is not None
            and ts is not None
            and (ts - prev_ts) > time_gap_s
        ):
            segments.append(cur)
            cur = []
        cur.append(i)
        prev_ts = ts if ts is not None else prev_ts
    if cur:
        segments.append(cur)
    return segments


def _dbscan_gps(
    points: list[tuple[float, float]], eps_km: float, min_samples: int
) -> list[int]:
    """Hand-rolled DBSCAN over haversine distance.

    Returns a label per point: ``>=0`` cluster id, ``-1`` for noise.
    """
    n = len(points)
    labels = [-1] * n
    visited = [False] * n

    def region(p: int) -> list[int]:
        return [q for q in range(n) if haversine_km(points[p], points[q]) <= eps_km]

    cluster = -1
    for p in range(n):
        if visited[p]:
            continue
        visited[p] = True
        neighbors = region(p)
        if len(neighbors) < min_samples:
            continue  # noise (may be claimed later as a border point)
        cluster += 1
        labels[p] = cluster
        seeds = list(neighbors)
        in_seeds = set(seeds)  # O(1) membership; avoids the O(n^2) re-scan
        idx = 0
        while idx < len(seeds):
            q = seeds[idx]
            idx += 1
            if not visited[q]:
                visited[q] = True
                q_neighbors = region(q)
                if len(q_neighbors) >= min_samples:
                    for r in q_neighbors:
                        if r not in in_seeds:
                            seeds.append(r)
                            in_seeds.add(r)
            if labels[q] == -1:
                labels[q] = cluster
    return labels


def _build_event(items: list[dict[str, Any]], member_idx: list[int]) -> Event:
    ids = [int(items[i]["id"]) for i in member_idx]
    tss = [
        items[i]["timestamp"]
        for i in member_idx
        if items[i].get("timestamp") is not None
    ]
    coords = [
        (items[i]["lat"], items[i]["lon"])
        for i in member_idx
        if items[i].get("lat") is not None and items[i].get("lon") is not None
    ]
    clat = sum(c[0] for c in coords) / len(coords) if coords else None
    clon = sum(c[1] for c in coords) / len(coords) if coords else None
    return Event(
        member_ids=sorted(ids),
        start=min(tss) if tss else None,
        end=max(tss) if tss else None,
        centroid_lat=clat,
        centroid_lon=clon,
    )


def cluster_events(
    items: list[dict[str, Any]],
    time_gap_s: float = DEFAULT_TIME_GAP_S,
    gps_eps_km: float = DEFAULT_GPS_EPS_KM,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> list[Event]:
    """Cluster ``items`` into events (auto-albums).

    Each item is ``{"id": int, "timestamp": float|None, "lat": float|None,
    "lon": float|None}``. See the module docstring for the algorithm. Returns a
    list of :class:`Event`, ordered by ``start`` (None last).
    """
    if not items:
        return []

    events: list[Event] = []
    for segment in _segment_by_time(items, time_gap_s):
        geo_idx = [
            i
            for i in segment
            if items[i].get("lat") is not None and items[i].get("lon") is not None
        ]
        non_geo = [i for i in segment if i not in geo_idx]

        if len(geo_idx) < min_samples:
            # Not enough GPS to split — the whole time segment is one event.
            events.append(_build_event(items, segment))
            continue

        pts = [(items[i]["lat"], items[i]["lon"]) for i in geo_idx]
        labels = _dbscan_gps(pts, gps_eps_km, min_samples)

        clusters: dict[int, list[int]] = {}
        noise: list[int] = []
        for local, lab in enumerate(labels):
            (noise if lab == -1 else clusters.setdefault(lab, [])).append(
                geo_idx[local]
            )

        if not clusters:
            # All GPS points were noise — keep the segment whole.
            events.append(_build_event(items, segment))
            continue

        # Fold noise + non-GPS items into the largest cluster in the segment.
        largest = max(clusters.values(), key=len)
        largest.extend(noise)
        largest.extend(non_geo)
        for member_idx in clusters.values():
            events.append(_build_event(items, member_idx))

    events.sort(key=lambda e: (e.start is None, e.start or 0.0))
    return events
