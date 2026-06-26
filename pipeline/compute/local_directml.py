"""Local DirectML backend — onnxruntime-directml with the DirectML EP.

Windows + AMD/Intel GPUs (and AMD-on-Windows, which has NO ROCm wheels — design
§2 AMD-on-Windows caveat). CV tiers run through ORT's ``DmlExecutionProvider``
(CPU fallback always appended). DirectML is in Microsoft "sustained engineering"
(WinML is the longevity open question) and wants Python <=3.11 while we run 3.14
(open decision 2) — target it now, verify the wheel/Py combo at packaging.
Tier-2 captioning delegates to torch (DirectML/CPU) via the shared base.
``privacy="local"``.
"""

from __future__ import annotations

from typing import Any

from pipeline.compute.local_onnx_base import LocalONNXBackend
from pipeline.compute.registry import register


@register("local_directml")
class LocalDirectMLBackend(LocalONNXBackend):
    """AMD/Intel-on-Windows backend (onnxruntime-directml, DmlExecutionProvider)."""

    NAME = "local_directml"
    EP_PREFERENCE = ("DmlExecutionProvider",)

    def __init__(self, name: str = "local_directml", **kw: Any) -> None:
        super().__init__(name=name, **kw)
