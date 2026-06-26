"""Provider-agnostic compute seam (wave 1).

A capability-level interface (``embed / tag / caption / detect``) over a
``list[ImageRef]``, with a registry + config-driven dispatcher and a privacy
gate. Concrete adapters (``local_mps``, ``rented_metal``) self-register on
import — importing this package registers them.

Public surface::

    from pipeline.compute import (
        Capability, ImageRef, ComputeBackend, ComputeDispatcher, make, register,
    )
"""

from __future__ import annotations

from pipeline.compute import local_cpu as _local_cpu  # noqa: E402,F401

# Cross-platform local adapters (Spec D). Each wraps ONNX Runtime with a
# different execution provider; all import-cheap (heavy deps lazy inside methods).
from pipeline.compute import local_cuda as _local_cuda  # noqa: E402,F401
from pipeline.compute import local_directml as _local_directml  # noqa: E402,F401

# Import the adapters so their @register side effects fire. Both are
# import-cheap (heavy deps are lazy-loaded inside methods).
from pipeline.compute import local_mps as _local_mps  # noqa: E402,F401
from pipeline.compute import rented_metal as _rented_metal  # noqa: E402,F401
from pipeline.compute.base import (
    BaseBackend,
    Capability,
    Caption,
    ComputeBackend,
    CostEstimate,
    Health,
    ImageRef,
    Regions,
    TagSet,
    Vector,
)
from pipeline.compute.dispatcher import ComputeDispatcher, PrivacyGateError
from pipeline.compute.registry import (
    ComputeConfig,
    load_compute_config,
    make,
    parse_compute_config,
    register,
    registered_names,
)

__all__ = [
    "BaseBackend",
    "Capability",
    "Caption",
    "ComputeBackend",
    "ComputeConfig",
    "ComputeDispatcher",
    "CostEstimate",
    "Health",
    "ImageRef",
    "PrivacyGateError",
    "Regions",
    "TagSet",
    "Vector",
    "load_compute_config",
    "make",
    "parse_compute_config",
    "register",
    "registered_names",
]
