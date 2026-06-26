"""Tests for Lane A (faces) — pure logic + API against a TEMP db only.

NEVER touches the real data/catalog.db. Each test builds a fresh temp sqlite db
and applies data/migrations/009_faces.sql to it. Heavy/optional deps (pyobjc /
Vision, onnxruntime + model file) are skipif-guarded so the suite stays green on
any box.

Mirrors tests/test_self_retrieval.py: repo root is inserted on sys.path FIRST so
the worktree's code (not any installed copy) is exercised.
"""

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.faces import cluster as cl  # noqa: E402
from pipeline.faces.embedder import l2_normalize, make_embedder  # noqa: E402
from pipeline.faces.store import (  # noqa: E402
    FaceStore,
    pack_embedding,
    unpack_embedding,
)

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = REPO_ROOT / "data" / "migrations" / "009_faces.sql"


# --------------------------------------------------------------------------- #
# fixtures — fresh temp db with migration 009 (+ a minimal images table).      #
# --------------------------------------------------------------------------- #
@pytest.fixture
def temp_db(tmp_path) -> str:
    db = tmp_path / "faces_test.db"
    conn = sqlite3.connect(str(db))
    # Minimal images table so the faces FK references something real. file_hash
    # is included because the store now joins it for thumbnail rendering.
    conn.execute(
        "CREATE TABLE images (id INTEGER PRIMARY KEY, path TEXT, file_hash TEXT)"
    )
    conn.executescript(MIGRATION.read_text())
    conn.executemany(
        "INSERT INTO images (id, path, file_hash) VALUES (?, ?, ?)",
        [(1, "library/a.jpg", "hash000000a1"), (2, "library/b.jpg", "hash000000b2")],
    )
    conn.commit()
    conn.close()
    return str(db)


def _vec(seed: int, dim: int = 128) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return l2_normalize(rng.standard_normal(dim).astype(np.float32))


def _jit(base: np.ndarray, scale: float = 0.01) -> np.ndarray:
    """A tiny random jitter of ``base`` (same dim), L2-normalized."""
    rng = np.random.default_rng(int(abs(base.sum() * 1e6)) % (2**32))
    return l2_normalize(
        base + scale * rng.standard_normal(base.shape[0]).astype(np.float32)
    )


# --------------------------------------------------------------------------- #
# migration applies + creates the expected tables.                            #
# --------------------------------------------------------------------------- #
def test_migration_creates_tables(temp_db):
    conn = sqlite3.connect(temp_db)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert {"people", "faces"} <= names


# --------------------------------------------------------------------------- #
# pack / unpack round-trip.                                                    #
# --------------------------------------------------------------------------- #
def test_pack_unpack_roundtrip():
    v = _vec(1)
    back = unpack_embedding(pack_embedding(v), 128)
    assert np.allclose(v, back, atol=1e-6)


def test_unpack_wrong_dim_raises():
    with pytest.raises(ValueError):
        unpack_embedding(pack_embedding(_vec(1)), 512)


# --------------------------------------------------------------------------- #
# store CRUD + person bookkeeping.                                            #
# --------------------------------------------------------------------------- #
def test_add_face_and_read_back(temp_db):
    store = FaceStore(temp_db)
    fid = store.add_face(
        image_id=1,
        bbox=[0.1, 0.2, 0.3, 0.4],
        embedding=_vec(1),
        embedding_dim=128,
        detector="apple_vision",
        embedder="sface",
        confidence=0.99,
    )
    assert fid > 0
    faces = store.faces_for_image(1)
    assert len(faces) == 1
    assert faces[0]["bbox"] == [0.1, 0.2, 0.3, 0.4]
    assert faces[0]["person_id"] is None


def test_create_assign_refreshes_person_count(temp_db):
    store = FaceStore(temp_db)
    pid = store.create_person("Alice")
    f1 = store.add_face(1, [0, 0, 1, 1], _vec(1), 128, "d", "sface", 0.9)
    f2 = store.add_face(2, [0, 0, 1, 1], _vec(2), 128, "d", "sface", 0.9)
    store.assign_face(f1, pid)
    store.assign_face(f2, pid)
    people = {p["id"]: p for p in store.list_people()}
    assert people[pid]["face_count"] == 2
    assert people[pid]["cover_face_id"] == f1
    assert people[pid]["name"] == "Alice"


def test_merge_split(temp_db):
    store = FaceStore(temp_db)
    p1 = store.create_person("A")
    p2 = store.create_person("B")
    f1 = store.add_face(1, [0, 0, 1, 1], _vec(1), 128, "d", "sface", 0.9, person_id=p1)
    store.add_face(2, [0, 0, 1, 1], _vec(2), 128, "d", "sface", 0.9, person_id=p2)
    store.merge_people(p1, p2)
    people = {p["id"]: p for p in store.list_people()}
    assert p1 not in people  # source gone
    assert people[p2]["face_count"] == 2
    # split f1 back out into its own new person
    new_pid = store.split_face(f1)
    assert new_pid not in (p1, p2)
    assert store.faces_for_person(new_pid)[0]["id"] == f1
    assert {p["id"]: p for p in store.list_people()}[p2]["face_count"] == 1


# --------------------------------------------------------------------------- #
# ERASURE — biometric right-to-erasure.                                       #
# --------------------------------------------------------------------------- #
def test_delete_person_erases_faces(temp_db):
    store = FaceStore(temp_db)
    pid = store.create_person("Erase me")
    store.add_face(1, [0, 0, 1, 1], _vec(1), 128, "d", "sface", 0.9, person_id=pid)
    store.add_face(2, [0, 0, 1, 1], _vec(2), 128, "d", "sface", 0.9, person_id=pid)
    removed = store.delete_person(pid)
    assert removed == 2
    assert pid not in {p["id"] for p in store.list_people()}
    # the face vectors are gone, not orphaned
    conn = sqlite3.connect(temp_db)
    n = conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0]
    conn.close()
    assert n == 0


def test_purge_all_faces(temp_db):
    store = FaceStore(temp_db)
    pid = store.create_person()
    store.add_face(1, [0, 0, 1, 1], _vec(1), 128, "d", "sface", 0.9, person_id=pid)
    store.add_face(2, [0, 0, 1, 1], _vec(2), 128, "d", "sface", 0.9)
    removed = store.purge_all_faces()
    assert removed == 2
    assert store.list_people() == []


# --------------------------------------------------------------------------- #
# DBSCAN + incremental assignment.                                            #
# --------------------------------------------------------------------------- #
def test_dbscan_finds_two_clusters():
    # Two tight clusters around two anchors, well separated.
    a = l2_normalize(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    b = l2_normalize(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    jit = lambda base, s: l2_normalize(base + 0.01 * _vec(s, 3))  # noqa: E731
    vecs = [jit(a, 1), jit(a, 2), jit(a, 3), jit(b, 4), jit(b, 5), jit(b, 6)]
    labels = cl.dbscan(vecs, eps=0.10, min_samples=2)
    assert len({lab for lab in labels if lab >= 0}) == 2
    assert labels[0] == labels[1] == labels[2]
    assert labels[3] == labels[4] == labels[5]
    assert labels[0] != labels[3]


def test_dbscan_empty():
    assert cl.dbscan([]) == []


def _three_blobs_with_bridge() -> tuple[list[np.ndarray], list[int]]:
    """3 well-separated gaussian identity blobs + a few 'bridge' points between
    two of them. Single-link DBSCAN density-reaches across the bridge and merges
    the two blobs; complete-linkage agglomerative caps cluster diameter and keeps
    them apart. Returns (vectors, blob_index_per_real_point).
    """
    dim = 16
    rng = np.random.default_rng(42)
    anchors = [
        l2_normalize(np.eye(dim, dtype=np.float32)[0]),
        l2_normalize(np.eye(dim, dtype=np.float32)[1]),
        l2_normalize(np.eye(dim, dtype=np.float32)[2]),
    ]
    vecs: list[np.ndarray] = []
    blob_of: list[int] = []
    for bi, a in enumerate(anchors):
        for _ in range(15):
            vecs.append(
                l2_normalize(a + 0.05 * rng.standard_normal(dim).astype(np.float32))
            )
            blob_of.append(bi)
    # Bridge points on the geodesic between blob 0 and blob 1 — a chain DBSCAN
    # can walk, fully inside no single blob.
    for t in (0.35, 0.5, 0.65):
        bridge = l2_normalize((1 - t) * anchors[0] + t * anchors[1])
        vecs.append(bridge)
        blob_of.append(-1)  # bridge, belongs to no real identity
    return vecs, blob_of


def test_agglomerative_resists_chaining_where_dbscan_merges():
    vecs, blob_of = _three_blobs_with_bridge()

    # DBSCAN with an eps loose enough to span the bridge merges blob0 and blob1.
    db = cl.dbscan(vecs, eps=0.35, min_samples=2)
    real = [(i, b) for i, b in enumerate(blob_of) if b >= 0]
    db_label = {b: db[i] for i, b in real}
    # blob0 and blob1 collapse to ONE DBSCAN label (the chaining failure).
    assert db_label[0] == db_label[1], "expected DBSCAN to chain blob0+blob1"

    # Complete-linkage agglomerative at the same threshold keeps all 3 apart.
    ag = cl.agglomerative(vecs, distance_threshold=0.35, min_samples=2)
    by_blob: dict[int, set[int]] = {0: set(), 1: set(), 2: set()}
    for i, b in real:
        by_blob[b].add(ag[i])
    # Each blob is internally coherent (one dominant label) AND the three blobs
    # get three distinct labels — no merge across identities.
    dominant = {
        b: max(labs, key=lambda x: list(by_blob[b]).count(x))
        for b, labs in by_blob.items()
    }
    assert len({dominant[0], dominant[1], dominant[2]}) == 3, (
        f"agglomerative merged identities: {dominant}"
    )


def test_cluster_vectors_dispatch_and_unknown_algorithm():
    vecs, _ = _three_blobs_with_bridge()
    assert cl.cluster_vectors(vecs, algorithm="agglomerative", eps=0.35)
    assert cl.cluster_vectors(vecs, algorithm="dbscan", eps=0.10)
    with pytest.raises(ValueError):
        cl.cluster_vectors(vecs, algorithm="kmeans")


def test_agglomerative_empty_and_min_samples_noise():
    assert cl.agglomerative([]) == []
    # A lone vector far from everything is dropped to noise when min_samples=2.
    a = l2_normalize(np.eye(8, dtype=np.float32)[0])
    b = l2_normalize(np.eye(8, dtype=np.float32)[1])
    loner = l2_normalize(np.eye(8, dtype=np.float32)[7])
    labels = cl.agglomerative(
        [a, _jit(a), b, _jit(b), loner], distance_threshold=0.20, min_samples=2
    )
    assert labels[-1] == -1  # the loner is noise


def test_run_clustering_partitions_by_embedder(temp_db):
    """Two embedders' vectors never co-cluster — clustering is embedder-scoped."""
    store = FaceStore(temp_db)
    a = l2_normalize(np.array([1.0, 0.0, 0.0] + [0.0] * 125, dtype=np.float32))
    # sface faces around anchor a
    for s in (1, 2, 3):
        store.add_face(
            1, [0, 0, 1, 1], l2_normalize(a + 0.001 * _vec(s)), 128, "d", "sface", 0.9
        )
    # arcface faces at the SAME location but a different embedder name
    for s in (4, 5, 6):
        store.add_face(
            2, [0, 0, 1, 1], l2_normalize(a + 0.001 * _vec(s)), 128, "d", "arcface", 0.9
        )
    res_sface = cl.run_clustering(store, embedder="sface", eps=0.20, min_samples=2)
    assert res_sface.faces_considered == 3  # only the sface rows were pulled
    assert res_sface.clusters_created == 1
    # The arcface rows are still unclustered (a separate partition).
    res_arc = cl.run_clustering(store, embedder="arcface", eps=0.20, min_samples=2)
    assert res_arc.faces_considered == 3
    assert res_arc.clusters_created == 1


def test_assign_incremental_matches_nearest_centroid():
    a = l2_normalize(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    b = l2_normalize(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    centroids = {10: a, 20: b}
    near_a = l2_normalize(a + 0.01 * _vec(7, 3))
    far = l2_normalize(np.array([0.0, 0.0, 1.0], dtype=np.float32))
    out = cl.assign_incremental(centroids, [(1, near_a), (2, far)], match_dist=0.10)
    assert out == {1: 10}  # near_a matched person 10; far left unassigned


def test_run_clustering_creates_people(temp_db):
    store = FaceStore(temp_db)
    a = l2_normalize(np.array([1.0, 0.0, 0.0] + [0.0] * 125, dtype=np.float32))
    b = l2_normalize(np.array([0.0, 1.0, 0.0] + [0.0] * 125, dtype=np.float32))
    for s in (1, 2, 3):
        store.add_face(
            1, [0, 0, 1, 1], l2_normalize(a + 0.001 * _vec(s)), 128, "d", "sface", 0.9
        )
    for s in (4, 5, 6):
        store.add_face(
            2, [0, 0, 1, 1], l2_normalize(b + 0.001 * _vec(s)), 128, "d", "sface", 0.9
        )
    result = cl.run_clustering(store, embedder="sface", eps=0.10, min_samples=2)
    assert result.clusters_created == 2
    assert result.faces_assigned == 6
    assert len(store.list_people()) == 2


# --------------------------------------------------------------------------- #
# API — gate (403 when disabled) + happy path (200 when enabled), temp db.    #
# --------------------------------------------------------------------------- #
def _client(temp_db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from webui import routes_faces

    app = FastAPI()
    app.include_router(routes_faces.router)
    app.dependency_overrides[routes_faces.get_store] = lambda: FaceStore(temp_db)
    return TestClient(app), routes_faces


def test_api_403_when_disabled(temp_db, monkeypatch):
    monkeypatch.setenv("MP_FACES_ENABLED", "false")
    client, _ = _client(temp_db)
    assert client.get("/api/faces/people").status_code == 403
    assert client.post("/api/faces/cluster").status_code == 403
    assert client.delete("/api/faces/people/1").status_code == 403


def test_api_happy_path_when_enabled(temp_db, monkeypatch):
    monkeypatch.setenv("MP_FACES_ENABLED", "true")
    client, _ = _client(temp_db)

    store = FaceStore(temp_db)
    pid = store.create_person("Alice")
    fid = store.add_face(
        1, [0, 0, 1, 1], _vec(1), 128, "d", "sface", 0.9, person_id=pid
    )

    r = client.get("/api/faces/people")
    assert r.status_code == 200
    assert any(p["id"] == pid for p in r.json())

    r = client.get("/api/faces/images/1/faces")
    assert r.status_code == 200 and len(r.json()) == 1

    r = client.post(f"/api/faces/people/{pid}/name", json={"name": "Bob"})
    assert r.status_code == 200

    r = client.post(f"/api/faces/faces/{fid}/split")
    assert r.status_code == 200
    new_pid = r.json()["new_person_id"]

    r = client.post(
        "/api/faces/people/merge", json={"source_id": new_pid, "target_id": pid}
    )
    assert r.status_code == 200

    r = client.delete(f"/api/faces/people/{pid}")
    assert r.status_code == 200 and r.json()["faces_removed"] == 1


# --------------------------------------------------------------------------- #
# Optional: real SFace embedder (skipped unless onnxruntime + model present).  #
# --------------------------------------------------------------------------- #
def _sface_available() -> bool:
    try:
        import onnxruntime  # noqa: F401
    except Exception:
        return False
    from pipeline.faces.config import faces_config

    return Path(faces_config()["sface_model_path"]).exists()


@pytest.mark.skipif(
    not _sface_available(), reason="onnxruntime + SFace model not present"
)
def test_sface_embedder_constructs():
    from pipeline.faces.config import faces_config

    emb = make_embedder("sface", **faces_config())
    assert emb.dim == 128
    assert emb.license_commercial is True


# --------------------------------------------------------------------------- #
# Optional: Apple Vision detector (skipped unless pyobjc/Vision importable).   #
# --------------------------------------------------------------------------- #
def _vision_available() -> bool:
    try:
        import Quartz  # noqa: F401
        import Vision  # noqa: F401
    except Exception:
        return False
    return True


@pytest.mark.skipif(
    not _vision_available(), reason="pyobjc / macOS Vision not importable"
)
def test_vision_detector_constructs():
    from pipeline.faces.detector import make_detector

    det = make_detector("apple_vision")
    assert det.name == "apple_vision"


# --------------------------------------------------------------------------- #
# 5-point alignment (SFace expects template-aligned crops; raw bbox collapses   #
# identities — the documented under-segmentation). cv2-gated geometry tests.    #
# --------------------------------------------------------------------------- #
def _cv2_available() -> bool:
    try:
        import cv2  # noqa: F401
    except Exception:
        return False
    return True


def test_template_for_size_scales_proportionally():
    from pipeline.faces.embedder import _ARCFACE_TEMPLATE_112, _template_for_size

    assert np.allclose(_template_for_size(112), _ARCFACE_TEMPLATE_112)
    assert np.allclose(_template_for_size(224), _ARCFACE_TEMPLATE_112 * 2.0)


@pytest.mark.skipif(not _cv2_available(), reason="OpenCV not installed")
def test_align_5point_warps_landmarks_onto_template():
    """A known similarity (rotate+scale+translate) of the template must invert.

    Place dots at transformed template points in a big image; after alignment
    each template position should land on a bright (warped-dot) pixel — i.e. the
    estimated transform recovered the canonical pose.
    """
    import math

    import cv2

    from pipeline.faces.embedder import _ARCFACE_TEMPLATE_112, _align_5point

    size = 112
    h = w = 400
    theta = math.radians(20.0)
    scale = 2.5
    rot = np.array(
        [[math.cos(theta), -math.sin(theta)], [math.sin(theta), math.cos(theta)]]
    )
    src_px = (_ARCFACE_TEMPLATE_112 @ (scale * rot).T) + np.array([120.0, 90.0])

    img = np.zeros((h, w, 3), dtype=np.uint8)
    for x, y in src_px:
        cv2.circle(img, (int(round(x)), int(round(y))), 4, (255, 255, 255), -1)

    pts5_norm = [[float(x) / w, float(y) / h] for x, y in src_px]
    aligned = _align_5point(img, pts5_norm, size)

    assert aligned is not None
    assert aligned.shape == (size, size, 3)
    gray = aligned[..., 0].astype(np.float32)
    for tx, ty in _ARCFACE_TEMPLATE_112:
        y0, y1 = max(0, int(ty) - 6), int(ty) + 7
        x0, x1 = max(0, int(tx) - 6), int(tx) + 7
        assert gray[y0:y1, x0:x1].max() > 100.0, f"no dot near template ({tx},{ty})"
