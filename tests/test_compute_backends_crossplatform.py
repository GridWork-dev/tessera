"""Tests for the cross-platform compute backends (Spec D, design §2).

Covers the host-detector decision logic (mocked providers — NO real ORT probe),
the ``local_cuda``/``local_directml``/``local_cpu`` adapter construction +
capability advertisement, EP resolution, registry round-trip, and the pure
parity helpers in ``scripts/export_onnx.py``. Anything needing real execution
providers / model weights / torch / nudenet is guarded with ``skipif`` (mirrors
``tests/test_self_retrieval.py`` and ``tests/test_compute_seam.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.compute import detect  # noqa: E402
from pipeline.compute.base import Capability, ComputeBackend  # noqa: E402
from pipeline.compute.local_cpu import LocalCPUBackend  # noqa: E402
from pipeline.compute.local_cuda import LocalCUDABackend  # noqa: E402
from pipeline.compute.local_directml import LocalDirectMLBackend  # noqa: E402
from pipeline.compute.local_onnx_base import (  # noqa: E402
    ALL_CAPABILITIES,
    LocalONNXBackend,
)
from pipeline.compute.registry import is_registered, make  # noqa: E402

ALL_BACKENDS = [LocalCUDABackend, LocalDirectMLBackend, LocalCPUBackend]


# --------------------------------------------------------------------------- #
# Host-detector — mocked provider lists + platform (no real ORT probe).        #
# --------------------------------------------------------------------------- #
def test_detect_apple_silicon_coreml_picks_mps(monkeypatch):
    monkeypatch.setattr(detect, "is_apple_silicon", lambda: True)
    assert (
        detect.detect_backend([detect.EP_COREML, detect.EP_CPU]) == detect.BACKEND_MPS
    )


def test_detect_cuda_provider_picks_cuda(monkeypatch):
    monkeypatch.setattr(detect, "is_apple_silicon", lambda: False)
    assert detect.detect_backend([detect.EP_CUDA, detect.EP_CPU]) == detect.BACKEND_CUDA


def test_detect_tensorrt_provider_picks_cuda(monkeypatch):
    monkeypatch.setattr(detect, "is_apple_silicon", lambda: False)
    assert detect.detect_backend([detect.EP_TENSORRT]) == detect.BACKEND_CUDA


def test_detect_directml_on_windows_picks_directml(monkeypatch):
    monkeypatch.setattr(detect, "is_apple_silicon", lambda: False)
    monkeypatch.setattr(detect.platform, "system", lambda: "Windows")
    assert (
        detect.detect_backend([detect.EP_DIRECTML, detect.EP_CPU])
        == detect.BACKEND_DIRECTML
    )


def test_detect_directml_off_windows_falls_back_to_cpu(monkeypatch):
    # DmlExecutionProvider present but NOT on Windows -> cpu (Dml is Windows-only).
    monkeypatch.setattr(detect, "is_apple_silicon", lambda: False)
    monkeypatch.setattr(detect.platform, "system", lambda: "Linux")
    assert (
        detect.detect_backend([detect.EP_DIRECTML, detect.EP_CPU]) == detect.BACKEND_CPU
    )


def test_detect_no_providers_falls_back_to_cpu(monkeypatch):
    monkeypatch.setattr(detect, "is_apple_silicon", lambda: False)
    assert detect.detect_backend([]) == detect.BACKEND_CPU


def test_detect_coreml_without_apple_silicon_is_not_mps(monkeypatch):
    # CoreML EP listed but not Apple Silicon (defensive) -> not mps.
    monkeypatch.setattr(detect, "is_apple_silicon", lambda: False)
    assert detect.detect_backend([detect.EP_COREML]) == detect.BACKEND_CPU


def test_available_providers_never_raises():
    # Real call: returns a list (possibly empty), never raises, no heavy import.
    assert isinstance(detect.available_providers(), list)


def test_host_report_decision_matches_detect_backend():
    report = detect.host_report()
    assert report.backend == detect.detect_backend(report.available_providers)
    assert report.backend in {
        detect.BACKEND_MPS,
        detect.BACKEND_CUDA,
        detect.BACKEND_DIRECTML,
        detect.BACKEND_CPU,
    }


# --------------------------------------------------------------------------- #
# Backend construction + capability advertisement (cheap — no weights).        #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cls", ALL_BACKENDS)
def test_backend_construction_and_capabilities(cls):
    backend = cls()
    assert backend.name == cls.NAME
    assert backend.mode == "realtime"
    assert backend.privacy == "local"  # all local -> privacy gate passes uncensored
    assert backend.capabilities == ALL_CAPABILITIES
    # No model is loaded by construction (lazy accessors still None).
    assert backend._siglip_session is None  # noqa: SLF001 - asserting laziness
    assert backend._wd_session is None  # noqa: SLF001
    assert backend._detector is None  # noqa: SLF001


@pytest.mark.parametrize("cls", ALL_BACKENDS)
def test_backend_satisfies_protocol(cls):
    assert isinstance(cls(), ComputeBackend)


def test_ep_preference_distinct_per_backend():
    assert LocalCUDABackend.EP_PREFERENCE[0] == "TensorrtExecutionProvider"
    assert "CUDAExecutionProvider" in LocalCUDABackend.EP_PREFERENCE
    assert LocalDirectMLBackend.EP_PREFERENCE == ("DmlExecutionProvider",)
    assert LocalCPUBackend.EP_PREFERENCE == ("CPUExecutionProvider",)


def test_resolved_providers_always_includes_cpu_fallback():
    # On this box ORT only advertises CoreML/Azure/CPU, so a CUDA preference
    # resolves to CPU — proving the fallback. Needs onnxruntime importable.
    pytest.importorskip("onnxruntime")
    for cls in ALL_BACKENDS:
        providers = cls().resolved_providers()
        assert providers  # never empty
        assert providers[-1] == "CPUExecutionProvider" or "CPUExecutionProvider" in (
            providers
        )


def test_health_reports_eps_without_loading_weights():
    pytest.importorskip("onnxruntime")
    backend = LocalCPUBackend()
    health = backend.health()
    assert health.ok is True
    assert "local_cpu" in health.detail
    assert backend._siglip_session is None  # noqa: SLF001 - health didn't load weights


@pytest.mark.parametrize("cls", ALL_BACKENDS)
def test_cost_estimate_is_free_local(cls):
    est = cls().cost_estimate(10, Capability.EMBED)
    assert est.usd == 0.0
    assert est.n == 10


# --------------------------------------------------------------------------- #
# Registry: the new backends self-register on package import + make() works.   #
# --------------------------------------------------------------------------- #
def test_new_backends_self_register():
    import pipeline.compute  # noqa: F401 - triggers @register side effects

    for name in ("local_cuda", "local_directml", "local_cpu"):
        assert is_registered(name)


def test_registry_make_round_trip_for_new_backends():
    import pipeline.compute  # noqa: F401

    assert isinstance(make("local_cuda"), LocalCUDABackend)
    assert isinstance(make("local_directml"), LocalDirectMLBackend)
    assert isinstance(make("local_cpu"), LocalCPUBackend)


def test_constructor_name_override():
    # Direct construction allows a name override (config uses the registry key).
    assert LocalCPUBackend(name="cpu-1").name == "cpu-1"


def test_make_ignores_unknown_config_keys():
    import pipeline.compute  # noqa: F401

    # Forward-compatible config blocks must not break construction.
    backend = make("local_cuda", some_future_key=123)
    assert backend.name == "local_cuda"


# --------------------------------------------------------------------------- #
# siglip_preprocess — pure shape/range check (needs numpy + PIL, present).     #
# --------------------------------------------------------------------------- #
def test_siglip_preprocess_shape_and_range():
    import numpy as np
    from PIL import Image

    from pipeline.compute.local_onnx_base import siglip_preprocess

    img = Image.new("RGB", (640, 480), (200, 100, 50))
    x = siglip_preprocess(img)
    assert x.shape == (1, 3, 384, 384)
    assert x.dtype == np.float32
    # mean=0.5/std=0.5 maps [0,1] -> [-1, 1].
    assert -1.0001 <= float(x.min()) and float(x.max()) <= 1.0001


# --------------------------------------------------------------------------- #
# export_onnx pure parity helpers (NO weights, NO torch).                       #
# --------------------------------------------------------------------------- #
def test_cosine_distance_identical_is_zero():
    from scripts.export_onnx import cosine_distance

    assert cosine_distance([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(0.0)


def test_cosine_distance_orthogonal_is_one():
    from scripts.export_onnx import cosine_distance

    assert cosine_distance([1.0, 0.0], [0.0, 1.0]) == pytest.approx(1.0)


def test_max_abs_diff():
    from scripts.export_onnx import max_abs_diff

    assert max_abs_diff([1.0, 2.0, 5.0], [1.0, 2.0, 2.0]) == pytest.approx(3.0)


def test_parity_ok_within_and_outside_tolerance():
    from scripts.export_onnx import parity_ok

    assert parity_ok(1e-4, 1e-3) is True
    assert parity_ok(1e-3, 1e-3) is True  # inclusive
    assert parity_ok(1e-2, 1e-3) is False


def test_parity_result_ok_property():
    from scripts.export_onnx import ParityResult

    passing = ParityResult("m", "cosine_distance", 5e-4, 1e-3)
    failing = ParityResult("m", "cosine_distance", 5e-3, 1e-3)
    assert passing.ok is True
    assert failing.ok is False


# --------------------------------------------------------------------------- #
# NOTE: a real-weights ONNX embed smoke (SigLIP image-tower over a sample image)
# is a MANUAL, box-only check — it needs models/siglip-image-tower/model.onnx,
# produced by scripts/export_onnx.py and not in the repo. There is intentionally
# no automated test here: a stub that always pytest.skip()s only inflates the
# skip count without ever asserting.
# --------------------------------------------------------------------------- #
def test_onnx_base_is_abstract_subclass_seam():
    # The base itself is instantiable but carries the CPU-only default EP; the
    # subclasses are what get registered. Confirms the shared seam is real.
    base = LocalONNXBackend(name="bare")
    assert base.privacy == "local"
    assert base.EP_PREFERENCE == ("CPUExecutionProvider",)
