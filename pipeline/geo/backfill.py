"""Backfill orchestration for the geo lane (GPS -> places -> events -> scene tags).

Thin, resumable write-side glue. **Dry-run is the DEFAULT**: every stage returns
a count summary and writes nothing unless the caller explicitly passes
``dry_run=False``. Backing up ``data/catalog.db`` (``scripts/backup_db.sh``) is
the CALLER's responsibility — same contract as ``pipeline/centroid_tagger.py``.

The geo tables (``places`` / ``events`` / ``event_members``) and the additive
``images``/``videos`` GPS columns come from migration 010; this module assumes
that migration has been applied. Reads/writes go through plain ``sqlite3`` on the
single-writer catalog path, except scene tags which reuse
``Database.add_tags_scored`` so they land in the existing ``tags`` table.

Heavy / optional deps (``exiftool``, ``reverse_geocoder``, torch) are only
touched in the stage that needs them, lazily, so importing this module is cheap.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

from pipeline.geo import events as ev
from pipeline.geo import gps as gps_mod
from pipeline.geo import reverse_geocode as rgeo
from pipeline.geo import scene_tags as st
from pipeline.paths import resolve_image_path

logger = logging.getLogger(__name__)

_STAGES = ("gps", "places", "events", "scene_tags")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: Any) -> float | None:
    """A stored ``created_at`` (ISO string) -> epoch seconds, tolerant of None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except ValueError:
        return None


def backfill_gps(db: Any, *, dry_run: bool = True, limit: int | None = None) -> dict:
    """Extract GPS for images that have none; write ``gps_lat/gps_lon``.

    Returns ``{stage, candidates, located, written, dry_run}``.
    """
    conn = sqlite3.connect(db.db_path)
    try:
        q = "SELECT id, path FROM images WHERE gps_lat IS NULL"
        if limit:
            q += f" LIMIT {int(limit)}"
        rows = conn.execute(q).fetchall()
        id_by_abs = {str(resolve_image_path(p)): iid for iid, p in rows}
        located = gps_mod.extract_gps(list(id_by_abs.keys())) if id_by_abs else {}
        written = 0
        if not dry_run:
            for abs_path, (lat, lon) in located.items():
                conn.execute(
                    "UPDATE images SET gps_lat = ?, gps_lon = ? WHERE id = ?",
                    (lat, lon, id_by_abs[abs_path]),
                )
                written += 1
            conn.commit()
        return {
            "stage": "gps",
            "candidates": len(rows),
            "located": len(located),
            "written": written,
            "dry_run": dry_run,
        }
    finally:
        conn.close()


def backfill_places(db: Any, *, dry_run: bool = True) -> dict:
    """Reverse-geocode images with GPS but no place; upsert ``places``.

    Returns ``{stage, candidates, places_upserted, linked, dry_run}``.
    """
    conn = sqlite3.connect(db.db_path)
    try:
        rows = conn.execute(
            "SELECT id, gps_lat, gps_lon FROM images "
            "WHERE gps_lat IS NOT NULL AND place_id IS NULL"
        ).fetchall()
        if not rows:
            return _place_summary(0, 0, 0, dry_run)

        coords = [(lat, lon) for _, lat, lon in rows]
        resolved = rgeo.lookup(coords)
        keys = [rgeo.place_key(lat, lon) for _, lat, lon in rows]
        unique_keys = {k: resolved[i] for i, k in enumerate(keys)}

        if dry_run:
            return _place_summary(len(rows), len(unique_keys), 0, dry_run)

        now = _now()
        place_ids: dict[str, int] = {}
        for key, place in unique_keys.items():
            conn.execute(
                "INSERT OR IGNORE INTO places "
                "(place_key, name, admin1, admin2, cc, lat, lon, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    key,
                    place["name"],
                    place["admin1"],
                    place["admin2"],
                    place["cc"],
                    place["lat"],
                    place["lon"],
                    now,
                ),
            )
            pid = conn.execute(
                "SELECT id FROM places WHERE place_key = ?", (key,)
            ).fetchone()[0]
            place_ids[key] = pid
        linked = 0
        for (iid, _, _), key in zip(rows, keys):
            conn.execute(
                "UPDATE images SET place_id = ? WHERE id = ?", (place_ids[key], iid)
            )
            linked += 1
        conn.commit()
        return _place_summary(len(rows), len(unique_keys), linked, dry_run)
    finally:
        conn.close()


def _place_summary(candidates: int, upserted: int, linked: int, dry_run: bool) -> dict:
    return {
        "stage": "places",
        "candidates": candidates,
        "places_upserted": upserted,
        "linked": linked,
        "dry_run": dry_run,
    }


def backfill_events(
    db: Any,
    *,
    dry_run: bool = True,
    time_gap_s: float = ev.DEFAULT_TIME_GAP_S,
    gps_eps_km: float = ev.DEFAULT_GPS_EPS_KM,
    min_samples: int = ev.DEFAULT_MIN_SAMPLES,
) -> dict:
    """Cluster all images into events; upsert ``events`` + ``event_members``.

    Returns ``{stage, items, events, members, dry_run}``.
    """
    conn = sqlite3.connect(db.db_path)
    try:
        rows = conn.execute(
            "SELECT id, created_at, gps_lat, gps_lon FROM images"
        ).fetchall()
        items = [
            {
                "id": int(iid),
                "timestamp": _parse_ts(created),
                "lat": lat,
                "lon": lon,
            }
            for iid, created, lat, lon in rows
        ]
        clusters = ev.cluster_events(
            items,
            time_gap_s=time_gap_s,
            gps_eps_km=gps_eps_km,
            min_samples=min_samples,
        )
        members = sum(len(c.member_ids) for c in clusters)
        if dry_run:
            return _event_summary(len(items), len(clusters), members, dry_run)

        now = _now()
        for cluster in clusters:
            cur = conn.execute(
                "INSERT INTO events "
                "(start_time, end_time, centroid_lat, centroid_lon, member_count, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    _iso_or_none(cluster.start),
                    _iso_or_none(cluster.end),
                    cluster.centroid_lat,
                    cluster.centroid_lon,
                    len(cluster.member_ids),
                    now,
                ),
            )
            event_id = cur.lastrowid
            for owner_id in cluster.member_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO event_members "
                    "(event_id, owner_type, owner_id) VALUES (?, 'image', ?)",
                    (event_id, owner_id),
                )
                conn.execute(
                    "UPDATE images SET event_id = ? WHERE id = ?",
                    (event_id, owner_id),
                )
        conn.commit()
        return _event_summary(len(items), len(clusters), members, dry_run)
    finally:
        conn.close()


def _iso_or_none(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _event_summary(items: int, n_events: int, members: int, dry_run: bool) -> dict:
    return {
        "stage": "events",
        "items": items,
        "events": n_events,
        "members": members,
        "dry_run": dry_run,
    }


def backfill_scene_tags(
    db: Any,
    *,
    dry_run: bool = True,
    threshold: float = st.DEFAULT_THRESHOLD,
    top_k: int = st.DEFAULT_TOP_K,
    limit: int | None = None,
) -> dict:
    """Zero-shot scene tags over the stored SigLIP vectors; write ``tags``.

    Loads the SigLIP text tower ONCE (lazy, torch) to embed the scene vocabulary,
    then scores each image's ``vec_siglip_1152`` vector by cosine. Reuses
    ``Database.add_tags_scored`` (``category="scene"``,
    ``tag_source="siglip_zeroshot"``). Returns
    ``{stage, scored, tags_written, dry_run}``.
    """
    import numpy as np

    from pipeline.tier1_embedder import VEC_TABLE, open_vec_db

    label_mat = st.embed_labels(st.SCENE_VOCAB)
    labels = list(st.SCENE_LABELS)

    conn = open_vec_db(db.db_path)
    try:
        q = f"SELECT image_id, embedding FROM {VEC_TABLE} ORDER BY image_id"
        if limit:
            q += f" LIMIT {int(limit)}"
        rows = conn.execute(q).fetchall()
    finally:
        conn.close()

    scored = 0
    tags_written = 0
    pending: list[tuple[int, list[dict[str, Any]]]] = []
    for image_id, blob in rows:
        vec = np.frombuffer(blob, dtype=np.float32)
        hits = st.score_scene_tags(vec, label_mat, labels, threshold, top_k)
        if hits:
            scored += 1
            pending.append((int(image_id), hits))

    if not dry_run and pending:
        with db.get_session() as session:
            for image_id, hits in pending:
                db.add_tags_scored(
                    session,
                    image_id,
                    [
                        {
                            "category": st.TAG_CATEGORY,
                            "value": h["value"],
                            "confidence": h["confidence"],
                            "tag_source": st.TAG_SOURCE,
                        }
                        for h in hits
                    ],
                )
                tags_written += len(hits)
            session.commit()

    return {
        "stage": "scene_tags",
        "scored": scored,
        "tags_written": tags_written,
        "dry_run": dry_run,
    }


def run_stage(db: Any, stage: str, *, dry_run: bool = True, **kwargs: Any) -> dict:
    """Dispatch one backfill stage by name (the API's entry point)."""
    if stage == "gps":
        return backfill_gps(db, dry_run=dry_run, **kwargs)
    if stage == "places":
        return backfill_places(db, dry_run=dry_run, **kwargs)
    if stage == "events":
        return backfill_events(db, dry_run=dry_run, **kwargs)
    if stage == "scene_tags":
        return backfill_scene_tags(db, dry_run=dry_run, **kwargs)
    raise ValueError(f"unknown backfill stage {stage!r}; expected one of {_STAGES}")
