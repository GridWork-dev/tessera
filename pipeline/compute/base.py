"""Compute seam — the provider-agnostic ``ComputeBackend`` interface.

A **capability-level** interface (NOT chat-completion-shaped): backends declare
which of {EMBED, TAG, CAPTION, DETECT} they can run and over what trust boundary
they run it. The unit of work is a ``list[ImageRef]`` per capability call.

This module is PURE: it defines the protocol + supporting types and imports no
heavy ML deps and no concrete backend. Concrete adapters (``local_mps``,
``rented_metal``) implement ``ComputeBackend`` and self-register via the
registry.

Privacy is a first-class attribute, not an afterthought: ``privacy`` tells the
dispatcher whether a backend is ``local`` (pixels never leave the box),
``private-infra`` (your own rented endpoint), or ``hosted-moderated`` (a
third-party API that may refuse/inspect content). The dispatcher's privacy gate
keys off this — an uncensored job must never reach a ``hosted-moderated``
backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pipeline.paths import resolve_image_path

Mode = Literal["batch", "realtime"]
Privacy = Literal["local", "private-infra", "hosted-moderated"]


class Capability(str, Enum):
    """The four pipeline capabilities a backend may advertise.

    Mirrors the Tier 0-3 split: tags / embeddings / captions / NudeNet regions.
    ``str`` mixin so values round-trip cleanly through ``config.yaml``.
    """

    EMBED = "embed"
    TAG = "tag"
    CAPTION = "caption"
    DETECT = "detect"


@dataclass(frozen=True)
class ImageRef:
    """A reference to one catalog image.

    Wraps the DB-relative path (paths are stored RELATIVE to the content root)
    and resolves through ``pipeline/paths.py`` — the same single source of truth
    every other consumer uses. ``image_id`` is optional so a backend can echo it
    back on the result row, but the privacy boundary holds either way: only the
    pixel bytes ever leave the box, never the path/filename.
    """

    rel_path: str
    image_id: int | None = None

    def resolve(self) -> Path:
        """DB-relative path -> absolute filesystem path (via ``paths.py``)."""
        return resolve_image_path(self.rel_path)


@dataclass(frozen=True)
class Vector:
    """One embedding result (Tier 1 ``embed``). ``values`` is L2-normalized."""

    image_id: int | None
    values: list[float]
    dim: int
    model: str


@dataclass(frozen=True)
class TagSet:
    """Structured tags for one image (Tier 0 ``tag``).

    ``tags`` mirrors the rows the tagger persists:
    ``{"category", "value", "confidence", "tag_source"}``.
    """

    image_id: int | None
    tags: list[dict[str, Any]]


@dataclass(frozen=True)
class Caption:
    """A free-text caption for one image (Tier 2 ``caption``)."""

    image_id: int | None
    text: str
    model: str


@dataclass(frozen=True)
class Regions:
    """NudeNet region metadata for one image (Tier 3 ``detect``).

    ``regions`` is the stored schema: ``{"label", "score", "box":[x1,y1,x2,y2]}``.
    Metadata only — NEVER a gate, per the pipeline invariant.
    """

    image_id: int | None
    regions: list[dict[str, Any]]


@dataclass(frozen=True)
class Health:
    """Result of a backend reachability check."""

    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class CostEstimate:
    """A rough cost estimate for running ``n`` items of one capability.

    ``usd`` may be ``0.0`` for local compute; ``capped`` is ``True`` when a
    caller-supplied ``cap`` would be exceeded (so the dispatcher can refuse).
    """

    usd: float
    n: int
    capability: Capability
    capped: bool = False
    detail: str = ""


@runtime_checkable
class ComputeBackend(Protocol):
    """Provider-agnostic compute backend.

    A backend advertises ``capabilities`` and implements one method per
    capability over a ``list[ImageRef]``. It need only implement the
    capabilities it advertises; the dispatcher checks ``capabilities`` before
    dispatch and raises for anything unsupported, so unsupported methods may
    simply raise ``NotImplementedError``.

    Attributes:
        name: registry key (matches ``register(name)`` / ``config.yaml``).
        capabilities: the subset of ``Capability`` this backend can run.
        mode: ``"batch"`` (offline, e.g. rented metal) or ``"realtime"`` (local).
        privacy: trust boundary — drives the dispatcher's privacy gate.
    """

    name: str
    capabilities: set[Capability]
    mode: Mode
    privacy: Privacy

    def embed(self, refs: list[ImageRef]) -> list[Vector]: ...

    def tag(self, refs: list[ImageRef]) -> list[TagSet]: ...

    def caption(self, refs: list[ImageRef]) -> list[Caption]: ...

    def detect(self, refs: list[ImageRef]) -> list[Regions]: ...

    def health(self) -> Health: ...

    def cost_estimate(self, n: int, cap: Capability) -> CostEstimate: ...


# Method name on a ComputeBackend that runs a given capability.
CAPABILITY_METHODS: dict[Capability, str] = {
    Capability.EMBED: "embed",
    Capability.TAG: "tag",
    Capability.CAPTION: "caption",
    Capability.DETECT: "detect",
}


@dataclass
class BaseBackend:
    """Optional convenience base: stores the common attrs + sane defaults.

    Adapters may subclass this to inherit attribute storage and a no-cost
    ``cost_estimate`` / unsupported-capability stubs, then override only the
    capabilities they actually run. Pure — no heavy imports here.
    """

    name: str
    capabilities: set[Capability] = field(default_factory=set)
    mode: Mode = "realtime"
    privacy: Privacy = "local"

    def _unsupported(self, cap: Capability) -> None:
        raise NotImplementedError(
            f"backend {self.name!r} does not support capability {cap.value!r}"
        )

    def embed(self, refs: list[ImageRef]) -> list[Vector]:
        self._unsupported(Capability.EMBED)
        raise AssertionError  # pragma: no cover — _unsupported always raises

    def tag(self, refs: list[ImageRef]) -> list[TagSet]:
        self._unsupported(Capability.TAG)
        raise AssertionError  # pragma: no cover

    def caption(self, refs: list[ImageRef]) -> list[Caption]:
        self._unsupported(Capability.CAPTION)
        raise AssertionError  # pragma: no cover

    def detect(self, refs: list[ImageRef]) -> list[Regions]:
        self._unsupported(Capability.DETECT)
        raise AssertionError  # pragma: no cover

    def health(self) -> Health:
        return Health(ok=True)

    def cost_estimate(self, n: int, cap: Capability) -> CostEstimate:
        return CostEstimate(usd=0.0, n=n, capability=cap)
