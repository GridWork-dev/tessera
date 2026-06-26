"""Local CUDA backend — onnxruntime-gpu with the CUDA/TensorRT EP.

Win/Linux + NVIDIA (design §2). CV tiers (TAG/EMBED/DETECT) run through ONNX
Runtime's CUDA EP (TensorRT preferred when present), CPU fallback always
appended. Tier-2 captioning delegates to the torch/transformers VLM via the
shared base. ``privacy="local"`` — pixels never leave the box.

Heavy deps load lazily (see ``local_onnx_base``); construction is cheap.
"""

from __future__ import annotations

from typing import Any

from pipeline.compute.local_onnx_base import LocalONNXBackend
from pipeline.compute.registry import register


@register("local_cuda")
class LocalCUDABackend(LocalONNXBackend):
    """NVIDIA GPU backend (onnxruntime-gpu, CUDA/TensorRT EP)."""

    NAME = "local_cuda"
    # TensorRT first when available (fastest), else CUDA, else CPU (base appends).
    EP_PREFERENCE = ("TensorrtExecutionProvider", "CUDAExecutionProvider")

    def __init__(self, name: str = "local_cuda", **kw: Any) -> None:
        super().__init__(name=name, **kw)
