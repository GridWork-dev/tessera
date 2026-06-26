"""Tests for Lane B — geo/places + events.

Pure-logic tests (GPS math, place keys, event clustering, scene-tag scoring) run
with no optional deps. The migration test applies 010 to a FRESH temp DB (never
``data/catalog.db``). API tests mount the bare ``routes_geo.router`` on a
throwaway FastAPI app pointed at the temp DB. Heavy/optional deps
(``pyexiftool`` / ``reverse_geocoder`` / torch) are skipif-guarded; no network.
"""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.geo import events as ev  # noqa: E402
from pipeline.geo import gps as gps_mod  # noqa: E402
from pipeline.geo import reverse_geocode as rgeo  # noqa: E402
from pipeline.geo import scene_tags as st  # noqa: E402

MIGRATION_010 = (
    Path(__file__).parent.parent / "data" / "migrations" / "010_geo_events.sql"
)

_HAS_EXIFTOOL = importlib.util.find_spec("exiftool") is not None
_HAS_RGEO = importlib.util.find_spec("reverse_geocoder") is not None
_HAS_TORCH = importlib.util.find_spec("torch") is not None


def _apply_migration_010(db) -> None:
    """Apply migration 010 to a temp DB whose ORM schema already exists."""
    sql = MIGRATION_010.read_text(encoding="utf-8")
    conn = sqlite3.connect(db.db_path)
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Migration 010 — additive tables + columns on a fresh temp DB.                #
# --------------------------------------------------------------------------- #
def test_migration_creates_tables_and_columns(db):
    _apply_migration_010(db)
    conn = sqlite3.connect(db.db_path)
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {"places", "events", "event_members"} <= tables

        img_cols = {r[1] for r in conn.execute("PRAGMA table_info(images)").fetchall()}
        assert {"gps_lat", "gps_lon", "place_id", "event_id"} <= img_cols

        vid_cols = {r[1] for r in conn.execute("PRAGMA table_info(videos)").fetchall()}
        assert {"gps_lat", "gps_lon", "place_id", "event_id"} <= vid_cols
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# GPS parsing — pure.                                                          #
# --------------------------------------------------------------------------- #
def test_dms_to_decimal_north_is_positive():
    assert gps_mod.dms_to_decimal(37, 46, 29.64, "N") == pytest.approx(
        37.7749, abs=1e-3
    )


def test_dms_to_decimal_west_is_negative():
    assert gps_mod.dms_to_decimal(122, 25, 9.84, "W") == pytest.approx(
        -122.4194, abs=1e-3
    )


def test_dms_to_decimal_bad_input_is_none():
    assert gps_mod.dms_to_decimal("x", 0, 0, "N") is None


def test_parse_exif_gps_decimal_with_refs():
    tags = {
        "EXIF:GPSLatitude": 37.7749,
        "EXIF:GPSLatitudeRef": "N",
        "EXIF:GPSLongitude": 122.4194,
        "EXIF:GPSLongitudeRef": "W",
    }
    lat, lon = gps_mod.parse_exif_gps(tags)
    assert lat == pytest.approx(37.7749, abs=1e-4)
    assert lon == pytest.approx(-122.4194, abs=1e-4)


def test_parse_exif_gps_composite_already_signed():
    tags = {"Composite:GPSLatitude": 37.7749, "Composite:GPSLongitude": -122.4194}
    assert gps_mod.parse_exif_gps(tags) == pytest.approx((37.7749, -122.4194), abs=1e-4)


def test_parse_exif_gps_video_iso6709_string():
    tags = {"QuickTime:GPSCoordinates": "+37.7749-122.4194+010.000/"}
    lat, lon = gps_mod.parse_exif_gps(tags)
    assert lat == pytest.approx(37.7749, abs=1e-4)
    assert lon == pytest.approx(-122.4194, abs=1e-4)


def test_parse_exif_gps_missing_is_none():
    assert gps_mod.parse_exif_gps({"EXIF:Make": "Canon"}) is None
    assert gps_mod.parse_exif_gps({}) is None


# --------------------------------------------------------------------------- #
# Reverse geocode — pure helpers.                                             #
# --------------------------------------------------------------------------- #
def test_place_key_rounds_to_grid_and_dedupes():
    # ~10 m apart -> same key (3 dp ~= 110 m grid).
    assert rgeo.place_key(37.77490, -122.41941) == rgeo.place_key(37.77492, -122.41939)


def test_place_key_distinct_for_far_points():
    assert rgeo.place_key(37.7749, -122.4194) != rgeo.place_key(40.7128, -74.0060)


def test_normalize_result_maps_columns():
    out = rgeo.normalize_result(
        {
            "name": "San Francisco",
            "admin1": "California",
            "admin2": "",
            "cc": "US",
            "lat": "37.77",
            "lon": "-122.42",
        }
    )
    assert out["name"] == "San Francisco"
    assert out["cc"] == "US"
    assert out["lat"] == pytest.approx(37.77)


# --------------------------------------------------------------------------- #
# Events — pure clustering.                                                    #
# --------------------------------------------------------------------------- #
def test_haversine_km_known_distance():
    # SF -> NYC is ~4130 km.
    d = ev.haversine_km((37.7749, -122.4194), (40.7128, -74.0060))
    assert d == pytest.approx(4130, abs=80)


def test_cluster_splits_on_time_gap():
    day = 86400
    items = [
        {"id": 1, "timestamp": 0.0, "lat": None, "lon": None},
        {"id": 2, "timestamp": 60.0, "lat": None, "lon": None},
        {"id": 3, "timestamp": 3 * day, "lat": None, "lon": None},
        {"id": 4, "timestamp": 3 * day + 60, "lat": None, "lon": None},
    ]
    events = ev.cluster_events(items, time_gap_s=6 * 3600)
    assert len(events) == 2
    assert {tuple(e.member_ids) for e in events} == {(1, 2), (3, 4)}


def test_cluster_splits_distinct_places_in_one_segment():
    # Same hour, two clusters ~4000 km apart -> GPS-DBSCAN splits them.
    items = [
        {"id": 1, "timestamp": 0.0, "lat": 37.7749, "lon": -122.4194},
        {"id": 2, "timestamp": 60.0, "lat": 37.7750, "lon": -122.4195},
        {"id": 3, "timestamp": 120.0, "lat": 40.7128, "lon": -74.0060},
        {"id": 4, "timestamp": 180.0, "lat": 40.7129, "lon": -74.0061},
    ]
    events = ev.cluster_events(
        items, time_gap_s=6 * 3600, gps_eps_km=2.0, min_samples=2
    )
    member_sets = {tuple(e.member_ids) for e in events}
    assert member_sets == {(1, 2), (3, 4)}


def test_cluster_lone_point_folds_into_nearest():
    # Two tight points + one far singleton in the same segment -> one event,
    # the singleton folded into the (only) cluster (no orphan event).
    items = [
        {"id": 1, "timestamp": 0.0, "lat": 37.7749, "lon": -122.4194},
        {"id": 2, "timestamp": 60.0, "lat": 37.7750, "lon": -122.4195},
        {"id": 3, "timestamp": 120.0, "lat": 51.5074, "lon": -0.1278},
    ]
    events = ev.cluster_events(
        items, time_gap_s=6 * 3600, gps_eps_km=2.0, min_samples=2
    )
    assert len(events) == 1
    assert events[0].member_ids == [1, 2, 3]


def test_cluster_empty():
    assert ev.cluster_events([]) == []


def test_cluster_centroid_is_mean_of_members():
    items = [
        {"id": 1, "timestamp": 0.0, "lat": 10.0, "lon": 20.0},
        {"id": 2, "timestamp": 60.0, "lat": 12.0, "lon": 22.0},
    ]
    events = ev.cluster_events(items, min_samples=2)
    assert events[0].centroid_lat == pytest.approx(11.0)
    assert events[0].centroid_lon == pytest.approx(21.0)


# --------------------------------------------------------------------------- #
# Scene tags — pure scoring.                                                   #
# --------------------------------------------------------------------------- #
def _unit(v):
    a = np.asarray(v, dtype=np.float32)
    return a / np.linalg.norm(a)


def test_score_scene_tags_picks_aligned_label():
    labels = ["beach", "forest", "city"]
    label_mat = np.stack([_unit([1, 0, 0]), _unit([0, 1, 0]), _unit([0, 0, 1])])
    img = _unit([0.9, 0.1, 0.0])
    hits = st.score_scene_tags(img, label_mat, labels, threshold=0.1, top_k=3)
    assert hits[0]["value"] == "beach"
    # descending confidence
    confs = [h["confidence"] for h in hits]
    assert confs == sorted(confs, reverse=True)


def test_score_scene_tags_threshold_and_topk():
    labels = ["a", "b", "c"]
    label_mat = np.stack([_unit([1, 0, 0]), _unit([0.7, 0.7, 0]), _unit([0, 1, 0])])
    img = _unit([1, 0, 0])
    hits = st.score_scene_tags(img, label_mat, labels, threshold=0.5, top_k=1)
    assert len(hits) == 1
    assert hits[0]["value"] == "a"


def test_score_scene_tags_orthogonal_returns_none():
    labels = ["a", "b"]
    label_mat = np.stack([_unit([1, 0, 0]), _unit([0, 1, 0])])
    img = _unit([0, 0, 1])
    assert st.score_scene_tags(img, label_mat, labels, threshold=0.1) == []


def test_score_scene_tags_dim_mismatch_raises():
    with pytest.raises(ValueError):
        st.score_scene_tags(
            np.zeros(3, dtype=np.float32),
            np.zeros((2, 4), dtype=np.float32),
            ["a", "b"],
        )


def test_scene_vocab_labels_aligned():
    assert len(st.SCENE_VOCAB) == len(st.SCENE_LABELS)


# --------------------------------------------------------------------------- #
# API — bare router on a throwaway app, pointed at a temp DB.                  #
# --------------------------------------------------------------------------- #
@pytest.fixture
def geo_app(db):
    """A FastAPI app mounting routes_geo.router against a seeded temp DB."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from webui import routes_geo

    _apply_migration_010(db)
    _seed_geo(db)
    routes_geo.set_database(db)

    app = FastAPI()
    app.include_router(routes_geo.router)
    client = TestClient(app)
    yield client
    routes_geo.set_database(None)  # type: ignore[arg-type]


def _seed_geo(db) -> None:
    conn = sqlite3.connect(db.db_path)
    try:
        conn.execute(
            "INSERT INTO places (id, place_key, name, admin1, cc, lat, lon) "
            "VALUES (1, '37.775,-122.419', 'San Francisco', 'California', 'US', 37.775, -122.419)"
        )
        conn.execute(
            "INSERT INTO images "
            "(id, path, media_type, processed, has_metadata, has_thumbnail, "
            "flagged, nudenet_checked, gps_lat, gps_lon, place_id) "
            "VALUES (1, 'library/x/_unsorted/a.jpg', 'image', 1, 0, 0, 0, 0, "
            "37.775, -122.419, 1)"
        )
        conn.execute(
            "INSERT INTO events (id, start_time, end_time, centroid_lat, centroid_lon, "
            "member_count) VALUES (1, '2026-01-01T00:00:00', '2026-01-01T01:00:00', "
            "37.775, -122.419, 1)"
        )
        conn.execute(
            "INSERT INTO event_members (event_id, owner_type, owner_id) "
            "VALUES (1, 'image', 1)"
        )
        conn.commit()
    finally:
        conn.close()


def test_api_list_places(geo_app):
    resp = geo_app.get("/api/geo/places")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["name"] == "San Francisco"
    assert data[0]["image_count"] == 1


def test_api_list_events(geo_app):
    resp = geo_app.get("/api/geo/events")
    assert resp.status_code == 200
    assert resp.json()[0]["member_count"] == 1


def test_api_event_detail(geo_app):
    resp = geo_app.get("/api/geo/events/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 1
    assert body["members"] == [{"owner_type": "image", "owner_id": 1}]


def test_api_event_detail_404(geo_app):
    assert geo_app.get("/api/geo/events/999").status_code == 404


def test_api_backfill_events_dry_run_writes_nothing(geo_app, db):
    resp = geo_app.post("/api/geo/backfill", json={"stage": "events", "dry_run": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "events"
    assert body["dry_run"] is True
    # No new events written (still just the seeded one).
    conn = sqlite3.connect(db.db_path)
    try:
        n = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        conn.close()
    assert n == 1


def test_api_backfill_unknown_stage_422(geo_app):
    resp = geo_app.post("/api/geo/backfill", json={"stage": "bogus"})
    assert resp.status_code == 422


def test_api_backfill_missing_stage_422(geo_app):
    resp = geo_app.post("/api/geo/backfill", json={})
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Backfill events end-to-end on the temp DB (no model / no network).           #
# --------------------------------------------------------------------------- #
def test_backfill_events_real_run_writes(db):
    from pipeline.geo import backfill as geo_backfill

    _apply_migration_010(db)
    conn = sqlite3.connect(db.db_path)
    try:
        cols = (
            "id, path, media_type, processed, has_metadata, has_thumbnail, "
            "flagged, nudenet_checked, created_at, gps_lat, gps_lon"
        )
        defaults = "'image', 1, 0, 0, 0, 0"
        conn.executemany(
            f"INSERT INTO images ({cols}) VALUES (?, ?, {defaults}, ?, ?, ?)",
            [
                (1, "a.jpg", "2026-01-01T00:00:00+00:00", 37.7749, -122.4194),
                (2, "b.jpg", "2026-01-01T00:01:00+00:00", 37.7750, -122.4195),
                (3, "c.jpg", "2026-02-01T00:00:00+00:00", 40.7128, -74.0060),
                (4, "d.jpg", "2026-02-01T00:01:00+00:00", 40.7129, -74.0061),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    summary = geo_backfill.backfill_events(db, dry_run=False)
    assert summary["events"] == 2
    assert summary["members"] == 4

    conn = sqlite3.connect(db.db_path)
    try:
        n_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        linked = conn.execute(
            "SELECT COUNT(*) FROM images WHERE event_id IS NOT NULL"
        ).fetchone()[0]
    finally:
        conn.close()
    assert n_events == 2
    assert linked == 4


# --------------------------------------------------------------------------- #
# Guarded — optional deps. Skip cleanly when absent; never hit the network.    #
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not _HAS_EXIFTOOL, reason="pyexiftool not installed")
def test_extract_gps_empty_paths_no_binary_needed():
    # Empty input short-circuits before any exiftool call.
    assert gps_mod.extract_gps([]) == {}


@pytest.mark.skipif(not _HAS_RGEO, reason="reverse_geocoder not installed")
def test_reverse_geocode_lookup_offline():
    out = rgeo.lookup([(37.7749, -122.4194)])
    assert len(out) == 1
    assert out[0]["cc"]  # some country resolved, fully offline


@pytest.mark.skipif(not _HAS_TORCH, reason="torch not installed")
def test_embed_labels_shape():
    mat = st.embed_labels(["a photo of a beach", "a photo of mountains"])
    assert mat.shape == (2, 1152)
