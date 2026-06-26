"""First-run model-weights delivery (Spec E).

Small, importable surface for the first-run wizard and CLI::

    from pipeline.weights import status, plan, pull, MANIFEST

CLI: ``python -m pipeline.weights status|plan|pull [--include-nudenet]``.
"""

from __future__ import annotations

from pipeline.weights.delivery import (
    hf_cache_dir,
    is_present,
    manifest_rows,
    models_root,
    plan,
    pull,
    status,
)
from pipeline.weights.manifest import (
    MANIFEST,
    ModelSpec,
    by_key,
    selected,
    total_size_mb,
)

__all__ = [
    "MANIFEST",
    "ModelSpec",
    "by_key",
    "hf_cache_dir",
    "is_present",
    "manifest_rows",
    "models_root",
    "plan",
    "pull",
    "selected",
    "status",
    "total_size_mb",
]
