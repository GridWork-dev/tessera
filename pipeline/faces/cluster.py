"""Clustering over face vectors (cosine distance; vectors are L2-normalized).

Two clusterers, selectable by name (see ``run_clustering(..., algorithm=...)``):

- ``"agglomerative"`` (DEFAULT) — complete-linkage agglomerative clustering with
  a cosine ``distance_threshold``. Complete linkage caps a cluster's *diameter*
  at the threshold (max pairwise distance ≤ T), so it is **immune to the
  single-link density chaining** that makes DBSCAN glue distinct identities into
  one mega-cluster. This is the right default for face identities: the corpus is
  well separated (only ~3% of random face pairs fall within cosine-dist 0.50),
  so a diameter cap partitions cleanly without a multi-thousand blob. One person
  may fragment into a few tight pose/lighting sub-clusters (recoverable via the
  merge UI); cross-identity contamination — the dangerous direction — does not
  happen. Implemented on ``scipy.cluster.hierarchy`` (no sklearn dependency).

- ``"dbscan"`` — classic full DBSCAN over cosine distance (self-written, pure
  numpy). Kept selectable, but on this corpus it single-link chains into a
  garbage mega-cluster at every eps, so it is no longer the default.

Online helpers:

- ``assign_incremental(centroids, vectors, match_dist)`` — cheap online step:
  assign each new vector to the nearest existing person centroid within
  ``match_dist``, else leave it (``None``) for the next full re-cluster.

``run_clustering`` ties it to a ``FaceStore``: pull the unclustered vectors for
one embedder, cluster them, create a ``people`` row per cluster, and assign
``person_id``. O(n²) is fine for the periodic job at corpus scale (tens of
thousands of faces).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pipeline.faces.store import FaceStore

# Default full-recluster algorithm. ``agglomerative`` (complete-linkage) is
# chaining-resistant; ``dbscan`` stays selectable for parity/debugging.
DEFAULT_ALGORITHM = "agglomerative"


def _cosine_dist_matrix(mat: np.ndarray) -> np.ndarray:
    """Pairwise cosine distance for L2-normalized rows: 1 - (mat @ mat.T)."""
    sims = mat @ mat.T
    np.clip(sims, -1.0, 1.0, out=sims)
    return 1.0 - sims


def dbscan(
    vectors: list[np.ndarray] | np.ndarray,
    eps: float = 0.30,
    min_samples: int = 2,
) -> list[int]:
    """Classic DBSCAN over cosine distance. Returns a label per vector (-1=noise)."""
    mat = np.asarray(vectors, dtype=np.float32)
    n = mat.shape[0]
    if n == 0:
        return []
    dist = _cosine_dist_matrix(mat)
    neighbors = [np.where(dist[i] <= eps)[0] for i in range(n)]

    labels = [-1] * n  # -1 = unvisited/noise
    visited = [False] * n
    cluster_id = -1
    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True
        if len(neighbors[i]) < min_samples:
            continue  # noise (may be claimed as a border point later)
        cluster_id += 1
        labels[i] = cluster_id
        seeds = list(neighbors[i])
        k = 0
        while k < len(seeds):
            j = int(seeds[k])
            if not visited[j]:
                visited[j] = True
                if len(neighbors[j]) >= min_samples:
                    seeds.extend(int(x) for x in neighbors[j])
            if labels[j] == -1:
                labels[j] = cluster_id
            k += 1
    return labels


def agglomerative(
    vectors: list[np.ndarray] | np.ndarray,
    distance_threshold: float = 0.45,
    min_samples: int = 2,
    linkage_method: str = "complete",
) -> list[int]:
    """Complete-linkage agglomerative clustering over cosine distance.

    Cuts the linkage tree at ``distance_threshold``: every returned cluster has
    max pairwise cosine distance ≤ the threshold (complete linkage), so clusters
    cannot chain the way DBSCAN's single-link density reachability does. Clusters
    with fewer than ``min_samples`` members are relabeled ``-1`` (noise), matching
    the DBSCAN return contract so ``run_clustering`` can treat the two
    interchangeably. Returns a label per vector (``-1`` = noise).

    Requires scipy (already a project dependency). ``linkage_method`` is exposed
    for experimentation but defaults to ``complete`` (the chaining-resistant one).
    """
    mat = np.asarray(vectors, dtype=np.float32)
    n = mat.shape[0]
    if n == 0:
        return []
    if n == 1:
        return [-1] if min_samples > 1 else [0]

    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import pdist

    # Condensed cosine-distance matrix; clamp tiny negatives from float error.
    dist = pdist(mat, metric="cosine")
    np.clip(dist, 0.0, 2.0, out=dist)
    z = linkage(dist, method=linkage_method)
    raw = fcluster(z, t=float(distance_threshold), criterion="distance")

    # Drop clusters below min_samples to noise; renumber survivors 0..k-1.
    counts: dict[int, int] = {}
    for lab in raw:
        counts[int(lab)] = counts.get(int(lab), 0) + 1
    remap: dict[int, int] = {}
    out: list[int] = []
    for lab in raw:
        lab = int(lab)
        if counts[lab] < min_samples:
            out.append(-1)
            continue
        if lab not in remap:
            remap[lab] = len(remap)
        out.append(remap[lab])
    return out


def cluster_vectors(
    vectors: list[np.ndarray] | np.ndarray,
    algorithm: str = DEFAULT_ALGORITHM,
    *,
    eps: float = 0.45,
    min_samples: int = 2,
) -> list[int]:
    """Dispatch to the selected clusterer. ``eps`` is the radius (DBSCAN) /
    cosine ``distance_threshold`` (agglomerative). Returns labels (-1 = noise)."""
    if algorithm == "dbscan":
        return dbscan(vectors, eps=eps, min_samples=min_samples)
    if algorithm == "agglomerative":
        return agglomerative(vectors, distance_threshold=eps, min_samples=min_samples)
    raise ValueError(
        f"unknown clustering algorithm {algorithm!r}; "
        "known: ['agglomerative', 'dbscan']"
    )


def assign_incremental(
    centroids: dict[int, np.ndarray],
    vectors: list[tuple[int, np.ndarray]],
    match_dist: float = 0.30,
) -> dict[int, int]:
    """Assign each (face_id, vector) to the nearest centroid within match_dist.

    Returns ``{face_id: person_id}`` for the faces that matched; unmatched faces
    are omitted (left for the next full re-cluster). ``centroids`` maps
    ``person_id -> L2-normalized centroid vector``.
    """
    if not centroids:
        return {}
    pids = list(centroids)
    cmat = np.asarray([centroids[p] for p in pids], dtype=np.float32)
    out: dict[int, int] = {}
    for face_id, vec in vectors:
        sims = cmat @ np.asarray(vec, dtype=np.float32)
        best = int(np.argmax(sims))
        if (1.0 - float(sims[best])) <= match_dist:
            out[face_id] = pids[best]
    return out


@dataclass(frozen=True)
class ClusterResult:
    """Outcome of a clustering run."""

    faces_considered: int
    clusters_created: int
    faces_assigned: int
    noise: int


def run_clustering(
    store: FaceStore,
    embedder: str,
    eps: float = 0.45,
    min_samples: int = 2,
    algorithm: str = DEFAULT_ALGORITHM,
) -> ClusterResult:
    """Full re-cluster of the unclustered faces for one embedder.

    Creates one ``people`` row per discovered cluster and assigns the member
    faces' ``person_id``. Noise faces stay unassigned. ``algorithm`` selects the
    clusterer (``agglomerative`` complete-linkage by default; ``dbscan`` legacy);
    ``eps`` is the cosine ``distance_threshold`` / DBSCAN radius respectively.
    """
    pending = store.unclustered_faces(embedder)
    if not pending:
        return ClusterResult(0, 0, 0, 0)
    face_ids = [fid for fid, _ in pending]
    vectors = [v for _, v in pending]
    labels = cluster_vectors(
        vectors, algorithm=algorithm, eps=eps, min_samples=min_samples
    )

    by_label: dict[int, list[int]] = {}
    for fid, lab in zip(face_ids, labels):
        if lab < 0:
            continue
        by_label.setdefault(lab, []).append(fid)

    assigned = 0
    for members in by_label.values():
        pid = store.create_person()
        for fid in members:
            store.assign_face(fid, pid)
            assigned += 1

    noise = sum(1 for lab in labels if lab < 0)
    return ClusterResult(
        faces_considered=len(face_ids),
        clusters_created=len(by_label),
        faces_assigned=assigned,
        noise=noise,
    )
