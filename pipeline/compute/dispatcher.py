"""Compute dispatcher — the seam's front door (FastAPI calls this).

Reads per-capability routes from ``config.yaml``, resolves the backend via the
registry, and enforces the **privacy gate**: a job marked ``uncensored`` must
NEVER route to a ``hosted-moderated`` backend (only ``local`` / ``private-infra``
are allowed). The gate is the privacy boundary the master spec calls out —
backends live behind the dispatcher and are never exposed directly.

Construction is cheap: backends are instantiated lazily on first use and cached,
so building a dispatcher does not load any heavy model.
"""

from __future__ import annotations

from typing import Any

from pipeline.compute.base import (
    CAPABILITY_METHODS,
    Capability,
    ComputeBackend,
    ImageRef,
)
from pipeline.compute.registry import ComputeConfig, load_compute_config, make

# Backends an uncensored job may use: pixels stay on infra you control.
UNCENSORED_SAFE_PRIVACY = {"local", "private-infra"}


class PrivacyGateError(RuntimeError):
    """Raised when a job's privacy requirement conflicts with the route."""


class ComputeDispatcher:
    """Routes capability work to the configured backend, enforcing privacy.

    Pass a ``ComputeConfig`` (parsed ``compute:`` block) or call
    ``ComputeDispatcher.from_config()`` to load it from ``config.yaml``. Backends
    are built on demand via the registry and cached by name.
    """

    def __init__(self, config: ComputeConfig) -> None:
        self.config = config
        self._cache: dict[str, ComputeBackend] = {}

    @classmethod
    def from_config(cls, config_path: str | None = None) -> ComputeDispatcher:
        cfg = (
            load_compute_config(config_path)
            if config_path is not None
            else load_compute_config()
        )
        return cls(cfg)

    def backend_for(self, cap: Capability) -> ComputeBackend:
        """Resolve (and cache) the backend configured for ``cap``."""
        name = self.config.backend_name_for(cap)
        if name not in self._cache:
            self._cache[name] = make(name, **self.config.backend_config(name))
        return self._cache[name]

    def run(
        self,
        cap: Capability,
        refs: list[ImageRef],
        *,
        uncensored: bool = False,
    ) -> list[Any]:
        """Run ``cap`` over ``refs`` via the configured backend.

        ``uncensored=True`` engages the privacy gate: the resolved backend must
        be ``local`` or ``private-infra`` — routing such a job to a
        ``hosted-moderated`` backend raises ``PrivacyGateError`` BEFORE any work
        (and before any pixel bytes leave the box).
        """
        backend = self.backend_for(cap)
        self._enforce_privacy_gate(backend, cap, uncensored=uncensored)

        if cap not in backend.capabilities:
            raise NotImplementedError(
                f"backend {backend.name!r} does not advertise capability "
                f"{cap.value!r} (routes point {cap.value!r} at it)"
            )
        method = getattr(backend, CAPABILITY_METHODS[cap])
        return method(refs)

    def cost_estimate(self, cap: Capability, n: int) -> Any:
        """Cost estimate for ``n`` items of ``cap`` on the configured backend."""
        return self.backend_for(cap).cost_estimate(n, cap)

    def health(self, cap: Capability) -> Any:
        """Health of the backend configured for ``cap``."""
        return self.backend_for(cap).health()

    # -- privacy gate ---------------------------------------------------------
    @staticmethod
    def _enforce_privacy_gate(
        backend: ComputeBackend, cap: Capability, *, uncensored: bool
    ) -> None:
        if not uncensored:
            return
        if backend.privacy not in UNCENSORED_SAFE_PRIVACY:
            raise PrivacyGateError(
                f"privacy gate: uncensored {cap.value!r} job cannot route to "
                f"backend {backend.name!r} (privacy={backend.privacy!r}); allowed "
                f"privacy levels for uncensored work: "
                f"{sorted(UNCENSORED_SAFE_PRIVACY)}"
            )
