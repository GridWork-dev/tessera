"""Faces config — the off-by-default opt-in switch + model paths.

Reads the ``faces:`` block from ``config.yaml`` with a SAFE default (feature
OFF). Never edits config. The ``MP_FACES_ENABLED`` env var overrides the file
flag so the feature can be opted into (or tests can enable it) without touching
the git-skip-worktree config.yaml.

Default ``faces:`` block the orchestrator should add to config.yaml::

    faces:
      enabled: false                 # OFF by default — biometric data is opt-in
      detector: apple_vision         # apple_vision (macOS Vision via pyobjc)
      embedder: sface                 # sface (Apache-2.0, 128-dim, commercial-safe) | arcface (NC)
      sface_model_path: models/face/face_recognition_sface_2021dec.onnx
      arcface_model_path: models/face/arcface_buffalo_l.onnx
      cluster_algorithm: agglomerative  # agglomerative (complete-linkage, chaining-resistant) | dbscan
      cluster_eps: 0.45              # cosine distance_threshold (agglo) / DBSCAN radius
      cluster_min_samples: 2         # min cluster size (smaller -> noise)
      match_dist: 0.30               # incremental nearest-centroid assignment radius

``cluster_algorithm`` defaults to ``agglomerative`` (complete-linkage): DBSCAN
single-link chains the well-separated face corpus into a garbage mega-cluster at
every eps, so it is no longer the default. ``cluster_eps`` is reused as the
agglomerative cosine ``distance_threshold`` (0.45 keeps clusters tight — mean
within-cluster cosine ~0.73 on the live arcface store).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from pipeline.paths import REPO_ROOT

DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"

# Safe defaults — the feature is dark unless explicitly enabled.
DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "detector": "apple_vision",
    "embedder": "sface",
    "sface_model_path": "models/face/face_recognition_sface_2021dec.onnx",
    "arcface_model_path": "models/face/arcface_buffalo_l.onnx",
    "cluster_algorithm": "agglomerative",
    "cluster_eps": 0.45,
    "cluster_min_samples": 2,
    "match_dist": 0.30,
}


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def faces_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Merge DEFAULTS with the ``faces:`` block from config.yaml (if any).

    Missing file or missing block -> DEFAULTS (feature OFF). Never raises on a
    missing config — faces stays safely dark.
    """
    merged = dict(DEFAULTS)
    try:
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        block = raw.get("faces") or {}
        merged.update(block)
    except FileNotFoundError:
        pass
    return merged


def faces_enabled(config_path: str | Path = DEFAULT_CONFIG_PATH) -> bool:
    """Is the faces feature opted-in?

    ``MP_FACES_ENABLED`` env var (if set) overrides the config flag — lets the
    feature be enabled without editing the git-skip-worktree config.yaml, and
    lets tests flip it per-process.
    """
    env = os.environ.get("MP_FACES_ENABLED")
    if env is not None:
        return _truthy(env)
    return _truthy(faces_config(config_path).get("enabled", False))
