"""Compute-backend registry — self-registration + config-driven factory.

Adapters self-register with the ``@register("name")`` decorator. ``make(name,
**cfg)`` instantiates one by name. ``load_compute_config`` reads the ``compute:``
block from ``config.yaml`` (``routes`` + ``backends``), so swapping a backend is
a config-value edit, not a code change.

Pure / lazy: importing this module does NOT import any concrete backend (and so
no torch / transformers). Callers must import the adapter modules they want
registered (``pipeline.compute`` does this in its ``__init__``), which triggers
their ``@register`` side effect.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, TypeVar

import yaml

from pipeline.compute.base import Capability, ComputeBackend
from pipeline.paths import REPO_ROOT

# name -> backend class (a callable that yields a ComputeBackend when called
# with its typed config kwargs).
_REGISTRY: dict[str, type] = {}

T = TypeVar("T")

DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"


def register(name: str) -> Callable[[type[T]], type[T]]:
    """Class decorator: register a backend under ``name``.

    Raises ``ValueError`` on a duplicate name so two adapters can't silently
    shadow each other.
    """

    def _decorator(cls: type[T]) -> type[T]:
        if name in _REGISTRY:
            raise ValueError(f"compute backend {name!r} already registered")
        _REGISTRY[name] = cls
        return cls

    return _decorator


def is_registered(name: str) -> bool:
    return name in _REGISTRY


def registered_names() -> list[str]:
    return sorted(_REGISTRY)


def make(name: str, **cfg: Any) -> ComputeBackend:
    """Instantiate a registered backend by name with its config kwargs.

    Raises ``KeyError`` (with the known names) for an unknown backend.
    """
    try:
        cls = _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown compute backend {name!r}; registered: {registered_names()}"
        ) from exc
    return cls(**cfg)


def _reset_registry() -> None:
    """Test hook: clear the registry. NOT for production use."""
    _REGISTRY.clear()


class ComputeConfig:
    """Parsed ``compute:`` block: per-capability routes + typed backend configs.

    ``routes`` maps a ``Capability`` to a backend name; ``backends`` maps a
    backend name to its kwargs dict (passed verbatim to ``make``).
    """

    def __init__(
        self,
        routes: dict[Capability, str],
        backends: dict[str, dict[str, Any]],
    ) -> None:
        self.routes = routes
        self.backends = backends

    def backend_name_for(self, cap: Capability) -> str:
        try:
            return self.routes[cap]
        except KeyError as exc:
            raise KeyError(f"no route configured for capability {cap.value!r}") from exc

    def backend_config(self, name: str) -> dict[str, Any]:
        return dict(self.backends.get(name, {}))


def parse_compute_config(raw: dict[str, Any]) -> ComputeConfig:
    """Build a ``ComputeConfig`` from the raw ``compute:`` mapping.

    Expected shape::

        compute:
          routes: {embed: local_mps, tag: local_mps, ...}
          backends:
            local_mps: {type: local_mps, ...}
            rented_metal: {type: rented_metal, base_url: ..., ...}

    Route capability keys are coerced to ``Capability``; unknown keys raise.
    """
    routes_raw = raw.get("routes", {}) or {}
    routes: dict[Capability, str] = {}
    for cap_key, backend_name in routes_raw.items():
        try:
            cap = Capability(cap_key)
        except ValueError as exc:
            valid = [c.value for c in Capability]
            raise ValueError(
                f"unknown capability {cap_key!r} in compute.routes; expected {valid}"
            ) from exc
        routes[cap] = backend_name
    backends = dict(raw.get("backends", {}) or {})
    return ComputeConfig(routes=routes, backends=backends)


def default_compute_config() -> ComputeConfig:
    """Host-adaptive default when no ``compute:`` block is configured.

    Routes every capability to the host-detected best local backend, falling back
    to ``local_cpu`` (available everywhere). Lets a clean install — shipping only
    ``defaults.yaml`` with no ``compute:`` block, or no repo ``config.yaml`` at all
    — build a dispatcher out of the box instead of failing closed (audit P0-4).
    """
    try:
        from pipeline.compute import detect

        backend = detect.host_report().backend
    except Exception:  # noqa: BLE001 — detector unavailable -> universal CPU fallback
        backend = "local_cpu"
    routes = {cap: backend for cap in Capability}
    return ComputeConfig(routes=routes, backends={backend: {"type": backend}})


def load_compute_config(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> ComputeConfig:
    """Read ``config.yaml`` and parse its ``compute:`` block.

    A missing file OR a missing ``compute:`` block falls back to
    ``default_compute_config()`` (host-detected) so a clean install can dispatch.
    """
    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        cfg = {}
    if "compute" not in cfg:
        return default_compute_config()
    return parse_compute_config(cfg["compute"])
