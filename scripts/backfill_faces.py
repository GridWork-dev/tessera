#!/usr/bin/env python3
"""Resumable faces backfill: detect (Apple Vision) -> embed (SFace) -> cluster.

Runs against whatever catalog the MEDIA_PIPELINE_* env seam points at (the live
catalog or an isolated staging instance). Writes biometric vectors to the
faces/people tables (migration 009).

RESUMABLE: images already present in ``faces`` are skipped, so re-running after an
interruption is safe (faceless images carry no marker, so they are re-detected on
resume — cheap, and a single full run does them once).

  ./venv/bin/python scripts/backfill_faces.py [--limit N] [--cluster-only]
      [--no-cluster] [--algorithm agglomerative|dbscan] [--eps E] [--min-samples M]

Run from the repo root so the relative SFace model path resolves. Apple Vision
detection is macOS-only. For the LIVE catalog, back up first:
``bash scripts/backup_db.sh``.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.faces.cluster import run_clustering  # noqa: E402
from pipeline.faces.config import faces_config  # noqa: E402
from pipeline.faces.detector import DetectorUnavailable, make_detector  # noqa: E402
from pipeline.faces.embedder import EmbedderUnavailable, make_embedder  # noqa: E402
from pipeline.faces.store import FaceStore  # noqa: E402
from pipeline.paths import resolve_image_path  # noqa: E402
from pipeline.settings import get_settings  # noqa: E402


def _pending_images(
    db_path: str, embedder: str, limit: int | None
) -> list[tuple[int, str]]:
    """(id, path) for images with no rows in ``faces`` yet FOR THIS EMBEDDER.

    Skip is embedder-scoped so an arcface pass over an sface-populated store
    re-detects (the two never compare; clustering partitions by embedder).
    """
    conn = sqlite3.connect(db_path)
    try:
        done = {
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT image_id FROM faces WHERE embedder = ?", (embedder,)
            )
        }
        rows = conn.execute("SELECT id, path FROM images ORDER BY id").fetchall()
    finally:
        conn.close()
    pending = [(int(i), p) for (i, p) in rows if int(i) not in done]
    return pending[:limit] if limit else pending


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Resumable faces detect+embed+cluster backfill"
    )
    ap.add_argument(
        "--limit", type=int, default=None, help="Cap images processed this run"
    )
    ap.add_argument(
        "--cluster-only",
        action="store_true",
        help="Skip detect/embed; just (re)cluster",
    )
    ap.add_argument(
        "--no-cluster", action="store_true", help="Detect/embed only; skip clustering"
    )
    ap.add_argument(
        "--algorithm",
        default=None,
        choices=["agglomerative", "dbscan"],
        help="Clusterer (default: faces config; agglomerative complete-linkage)",
    )
    ap.add_argument(
        "--eps",
        type=float,
        default=None,
        help="Override cluster_eps (agglo cosine distance_threshold / DBSCAN radius)",
    )
    ap.add_argument(
        "--min-samples", type=int, default=None, help="Override cluster_min_samples"
    )
    ap.add_argument(
        "--embedder",
        default=None,
        help="Embedder name (default: faces config; sface|arcface)",
    )
    args = ap.parse_args()

    settings = get_settings()
    db_path = str(settings.database_path)
    cfg = faces_config()
    embedder_name = str(args.embedder or cfg.get("embedder", "sface"))
    detector_name = str(cfg.get("detector", "apple_vision"))
    store = FaceStore(db_path)

    print(f"[faces] db={db_path}")
    print(f"[faces] detector={detector_name} embedder={embedder_name}")

    if not args.cluster_only:
        try:
            det = make_detector(detector_name)
            emb = make_embedder(embedder_name, **cfg)
        except (DetectorUnavailable, EmbedderUnavailable) as exc:
            print(f"[faces] FATAL: {exc}", file=sys.stderr)
            return 2
        pending = _pending_images(db_path, embedder_name, args.limit)
        print(f"[faces] {len(pending)} images to detect")
        t0 = time.time()
        n_imgs = n_faces = n_skip = 0
        for k, (image_id, rel) in enumerate(pending, 1):
            path = resolve_image_path(rel)
            if not path.exists():
                n_skip += 1
                continue
            try:
                faces = det.detect(path)
            except DetectorUnavailable:
                n_skip += 1
                continue
            if not faces:
                continue
            try:
                vecs = emb.embed(path, faces)
            except EmbedderUnavailable:
                n_skip += 1
                continue
            for face, vec in zip(faces, vecs):
                store.add_face(
                    image_id=image_id,
                    bbox=face.bbox,
                    embedding=vec,
                    embedding_dim=emb.dim,
                    detector=det.name,
                    embedder=emb.name,
                    confidence=face.confidence,
                )
                n_faces += 1
            n_imgs += 1
            if k % 25 == 0:
                print(
                    f"[faces] {k}/{len(pending)} imgs · {n_faces} faces · {time.time() - t0:.0f}s"
                )
        print(
            f"[faces] detect+embed done: {n_imgs} imgs w/ faces · {n_faces} faces · "
            f"{n_skip} skipped · {time.time() - t0:.0f}s"
        )

    if not args.no_cluster:
        eps = args.eps if args.eps is not None else float(cfg["cluster_eps"])
        ms = (
            args.min_samples
            if args.min_samples is not None
            else int(cfg["cluster_min_samples"])
        )
        algo = str(args.algorithm or cfg.get("cluster_algorithm", "agglomerative"))
        res = run_clustering(
            store, embedder_name, eps=eps, min_samples=ms, algorithm=algo
        )
        print(
            f"[faces] cluster: algo={algo} considered={res.faces_considered} "
            f"clusters={res.clusters_created} assigned={res.faces_assigned} "
            f"noise={res.noise} (eps={eps}, min_samples={ms})"
        )
        people = store.list_people()
        print(f"[faces] people now: {len(people)}")
        for p in people[:15]:
            print(f"  person {p['id']}: {p['face_count']} faces  name={p.get('name')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
