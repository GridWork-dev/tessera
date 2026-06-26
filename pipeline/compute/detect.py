"""Host-detector — pick the best local compute backend for THIS machine.

A small custom detector (the InstantHMR pattern: ``platform`` checks plus an
``onnxruntime.get_available_providers()`` probe), NOT a third-party installer
dep — ``torchruntime`` is a fast-follow only if the matrix grows, and DirectML
wants Python <=3.11 while we run 3.14 (design §2, open decision 2). The detector
runs once at first-run and writes the chosen backend name into the resolved
config so ``config.yaml`` stops being hand-edited and becomes machine-derived.

HEAVY-IMPORT RULE: nothing heavy at module load. ``platform`` is stdlib;
``onnxruntime`` is imported lazily inside ``available_providers()`` so importing
this module is cheap and safe on a box without onnxruntime installed.

Mapping (design §2 backend table):

  * macOS Apple Silicon (CoreML EP present) -> ``local_mps``
  * NVIDIA (CUDA/TensorRT EP present)        -> ``local_cuda``
  * Windows + DirectML EP present            -> ``local_directml``
  * anything else                            -> ``local_cpu``
"""

from __future__ import annotations

import platform
from dataclasses import dataclass

# Backend registry names this detector may return. Kept as plain strings (the
# detector must not import the concrete adapters — that would pull heavy deps).
BACKEND_MPS = "local_mps"
BACKEND_CUDA = "local_cuda"
BACKEND_DIRECTML = "local_directml"
BACKEND_CPU = "local_cpu"

# ONNX Runtime execution-provider names we probe for.
EP_COREML = "CoreMLExecutionProvider"
EP_CUDA = "CUDAExecutionProvider"
EP_TENSORRT = "TensorrtExecutionProvider"
EP_DIRECTML = "DmlExecutionProvider"
EP_CPU = "CPUExecutionProvider"


def available_providers() -> list[str]:
    """ONNX Runtime's available execution providers on this host (lazy import).

    Returns ``[]`` if onnxruntime is not importable, so the detector degrades to
    a platform-only decision instead of raising on a box without ORT.
    """
    try:
        import onnxruntime as ort
    except Exception:  # noqa: BLE001 - ORT missing/broken -> no providers known
        return []
    try:
        return list(ort.get_available_providers())
    except Exception:  # noqa: BLE001 - defensive: never raise from a probe
        return []


def is_apple_silicon() -> bool:
    """True on macOS running on an arm64 (Apple Silicon) CPU."""
    return platform.system() == "Darwin" and platform.machine().lower() in {
        "arm64",
        "aarch64",
    }


def detect_backend(providers: list[str] | None = None) -> str:
    """Return the registry name of the best local backend for this host.

    ``providers`` is injectable for tests (otherwise probed via
    ``available_providers()``). The decision order matches the design §2 table:
    Apple Silicon + CoreML -> mps; NVIDIA EPs -> cuda; Windows DirectML EP ->
    directml; else cpu.
    """
    if providers is None:
        providers = available_providers()
    provider_set = set(providers)

    # Apple Silicon: prefer the CoreML EP path (the existing local_mps backend).
    if is_apple_silicon() and EP_COREML in provider_set:
        return BACKEND_MPS

    # NVIDIA: CUDA or TensorRT EP present means an NVIDIA GPU + onnxruntime-gpu.
    if EP_CUDA in provider_set or EP_TENSORRT in provider_set:
        return BACKEND_CUDA

    # DirectML is Windows-only (AMD/Intel GPUs, or AMD-on-Windows via Dml).
    if EP_DIRECTML in provider_set and platform.system() == "Windows":
        return BACKEND_DIRECTML

    # Fallback: CPU EP works everywhere (and is always last in any EP list).
    return BACKEND_CPU


@dataclass(frozen=True)
class HostReport:
    """A snapshot of the detection inputs + decision (for the first-run wizard)."""

    system: str
    machine: str
    apple_silicon: bool
    available_providers: list[str]
    backend: str


def host_report() -> HostReport:
    """Gather the full detection context in one call (logging / first-run UX)."""
    providers = available_providers()
    return HostReport(
        system=platform.system(),
        machine=platform.machine(),
        apple_silicon=is_apple_silicon(),
        available_providers=providers,
        backend=detect_backend(providers),
    )
