"""Local CPU backend — onnxruntime with the CPU EP (universal fallback).

Any host with no usable GPU (design §2). CV tiers run on ``CPUExecutionProvider``
(slow — the first-run UI should warn); Tier-2 captioning delegates to torch-CPU
via the shared base. ``privacy="local"`` — pixels never leave the box, so the
dispatcher's privacy gate passes uncensored work by construction.

Heavy deps load lazily (see ``local_onnx_base``); construction is cheap.
"""

from __future__ import annotations

from typing import Any

from pipeline.compute.local_onnx_base import LocalONNXBackend
from pipeline.compute.registry import register


@register("local_cpu")
class LocalCPUBackend(LocalONNXBackend):
    """CPU-only backend (onnxruntime CPUExecutionProvider). Works everywhere."""

    NAME = "local_cpu"
    EP_PREFERENCE = ("CPUExecutionProvider",)

    def __init__(self, name: str = "local_cpu", **kw: Any) -> None:
        super().__init__(name=name, **kw)
