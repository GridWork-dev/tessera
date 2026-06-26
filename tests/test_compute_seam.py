"""Tests for the wave-1 compute seam (``pipeline/compute/``).

The protocol/registry/dispatcher logic is tested with a ``FakeBackend`` that
returns canned data — NO torch, NO real models, NO network. A guarded smoke test
covers ``LocalMPSBackend`` construction + capability advertisement; anything that
would load real weights is skipped via ``pytest.mark.skipif`` (mirrors
``tests/test_self_retrieval.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.compute.base import (  # noqa: E402
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
from pipeline.compute.dispatcher import (  # noqa: E402
    ComputeDispatcher,
    PrivacyGateError,
)
from pipeline.compute.registry import (  # noqa: E402
    ComputeConfig,
    is_registered,
    make,
    register,
    registered_names,
)


# --------------------------------------------------------------------------- #
# FakeBackend — canned data, no models / network. Used everywhere below.       #
# --------------------------------------------------------------------------- #
class FakeBackend:
    """A ComputeBackend that returns canned results. Privacy configurable."""

    def __init__(self, name: str = "fake", privacy: str = "local", **_):
        self.name = name
        self.privacy = privacy
        self.mode = "realtime"
        self.capabilities = {
            Capability.EMBED,
            Capability.TAG,
            Capability.CAPTION,
            Capability.DETECT,
        }
        self.calls: list[tuple[str, int]] = []

    def embed(self, refs: list[ImageRef]) -> list[Vector]:
        self.calls.append(("embed", len(refs)))
        return [Vector(r.image_id, [0.0, 1.0], 2, "fake") for r in refs]

    def tag(self, refs: list[ImageRef]) -> list[TagSet]:
        self.calls.append(("tag", len(refs)))
        return [TagSet(r.image_id, [{"category": "tags", "value": "x"}]) for r in refs]

    def caption(self, refs: list[ImageRef]) -> list[Caption]:
        self.calls.append(("caption", len(refs)))
        return [Caption(r.image_id, "a caption", "fake") for r in refs]

    def detect(self, refs: list[ImageRef]) -> list[Regions]:
        self.calls.append(("detect", len(refs)))
        return [Regions(r.image_id, []) for r in refs]

    def health(self) -> Health:
        return Health(ok=True, detail="fake")

    def cost_estimate(self, n: int, cap: Capability) -> CostEstimate:
        return CostEstimate(usd=0.0, n=n, capability=cap)


def test_fakebackend_satisfies_protocol():
    # runtime_checkable Protocol — structural conformance.
    assert isinstance(FakeBackend(), ComputeBackend)


# --------------------------------------------------------------------------- #
# Registry: register/make round-trip.                                          #
# --------------------------------------------------------------------------- #
def test_registry_register_make_round_trip():
    name = "fake_round_trip"

    @register(name)
    class _Reg(FakeBackend):
        pass

    assert is_registered(name)
    assert name in registered_names()
    backend = make(name)  # cfg kwargs would be passed to the constructor here
    assert isinstance(backend, _Reg)


def test_registry_make_unknown_raises():
    with pytest.raises(KeyError):
        make("definitely_not_registered")


def test_registry_duplicate_register_raises():
    @register("fake_dup")
    class _A(FakeBackend):
        pass

    with pytest.raises(ValueError):

        @register("fake_dup")
        class _B(FakeBackend):
            pass


# --------------------------------------------------------------------------- #
# Dispatcher routing: routes a capability to the configured backend.           #
# --------------------------------------------------------------------------- #
def _dispatcher_with(backend: FakeBackend) -> ComputeDispatcher:
    """A dispatcher whose every route resolves to the given pre-built backend."""
    config = ComputeConfig(
        routes={c: backend.name for c in Capability},
        backends={backend.name: {}},
    )
    dispatcher = ComputeDispatcher(config)
    # Inject the pre-built instance so we don't need it in the global registry.
    dispatcher._cache[backend.name] = backend  # noqa: SLF001 - test seam
    return dispatcher


def test_dispatcher_routes_capability_to_backend():
    backend = FakeBackend(name="routed")
    dispatcher = _dispatcher_with(backend)
    refs = [ImageRef("library/p/sfw/a.jpg", image_id=1)]

    out = dispatcher.run(Capability.CAPTION, refs)

    assert backend.calls == [("caption", 1)]
    assert isinstance(out[0], Caption)
    assert out[0].text == "a caption"


def test_dispatcher_run_each_capability():
    backend = FakeBackend(name="routed_all")
    dispatcher = _dispatcher_with(backend)
    refs = [ImageRef("library/p/sfw/a.jpg", image_id=1)]
    for cap in Capability:
        dispatcher.run(cap, refs)
    assert {c for c, _ in backend.calls} == {c.value for c in Capability}


def test_dispatcher_unsupported_capability_raises():
    backend = FakeBackend(name="no_embed")
    backend.capabilities = {Capability.TAG}  # advertise only TAG
    dispatcher = _dispatcher_with(backend)
    with pytest.raises(NotImplementedError):
        dispatcher.run(Capability.EMBED, [ImageRef("library/p/sfw/a.jpg")])


# --------------------------------------------------------------------------- #
# Privacy gate: uncensored job must never reach a hosted-moderated backend.    #
# --------------------------------------------------------------------------- #
def test_privacy_gate_blocks_uncensored_to_hosted_moderated():
    hosted = FakeBackend(name="hosted", privacy="hosted-moderated")
    dispatcher = _dispatcher_with(hosted)
    refs = [ImageRef("library/p/nsfw/a.jpg", image_id=1)]
    with pytest.raises(PrivacyGateError):
        dispatcher.run(Capability.CAPTION, refs, uncensored=True)
    # The job must be refused BEFORE the backend runs.
    assert hosted.calls == []


def test_privacy_gate_allows_uncensored_to_local():
    local = FakeBackend(name="local_fake", privacy="local")
    dispatcher = _dispatcher_with(local)
    out = dispatcher.run(
        Capability.CAPTION,
        [ImageRef("library/p/nsfw/a.jpg", image_id=1)],
        uncensored=True,
    )
    assert len(out) == 1


def test_privacy_gate_allows_uncensored_to_private_infra():
    infra = FakeBackend(name="infra_fake", privacy="private-infra")
    dispatcher = _dispatcher_with(infra)
    out = dispatcher.run(
        Capability.EMBED,
        [ImageRef("library/p/nsfw/a.jpg", image_id=1)],
        uncensored=True,
    )
    assert len(out) == 1


def test_privacy_gate_inactive_for_censored_jobs():
    # A non-uncensored job may route anywhere (the gate is opt-in).
    hosted = FakeBackend(name="hosted2", privacy="hosted-moderated")
    dispatcher = _dispatcher_with(hosted)
    out = dispatcher.run(Capability.TAG, [ImageRef("library/p/sfw/a.jpg")])
    assert len(out) == 1


# --------------------------------------------------------------------------- #
# ImageRef resolves through pipeline/paths.py.                                 #
# --------------------------------------------------------------------------- #
def test_imageref_resolves_relative_through_paths():
    from pipeline.paths import content_root

    ref = ImageRef("library/p/sfw/a.jpg", image_id=7)
    assert ref.resolve() == content_root() / "library/p/sfw/a.jpg"


# --------------------------------------------------------------------------- #
# Config parsing: routes + backends round-trip from the real config.yaml.      #
# --------------------------------------------------------------------------- #
def test_load_compute_config_from_repo_yaml():
    from pipeline.compute.registry import load_compute_config

    cfg = load_compute_config()
    # The shipped config routes every capability somewhere.
    for cap in Capability:
        assert cfg.backend_name_for(cap)
    assert "local_mps" in cfg.backends


def test_parse_compute_config_rejects_unknown_capability():
    from pipeline.compute.registry import parse_compute_config

    with pytest.raises(ValueError):
        parse_compute_config({"routes": {"bogus": "local_mps"}, "backends": {}})


# --------------------------------------------------------------------------- #
# Clean-install fallback (audit P0-4): a missing config file OR a yaml with no  #
# ``compute:`` block must still build a dispatchable config that routes every   #
# capability, instead of failing closed.                                        #
# --------------------------------------------------------------------------- #
def test_default_compute_config_routes_every_capability():
    from pipeline.compute.registry import default_compute_config

    cfg = default_compute_config()
    for cap in Capability:
        # Every capability resolves to a non-empty backend name...
        name = cfg.backend_name_for(cap)
        assert name
        # ...and that backend has a config block (so make() gets its kwargs).
        assert name in cfg.backends


def test_load_compute_config_missing_file_falls_back_to_default(tmp_path):
    from pipeline.compute.registry import default_compute_config, load_compute_config

    missing = tmp_path / "does_not_exist.yaml"
    cfg = load_compute_config(missing)
    # Identical routing to the host-detected default — every capability covered.
    default = default_compute_config()
    for cap in Capability:
        assert cfg.backend_name_for(cap) == default.backend_name_for(cap)


def test_load_compute_config_no_compute_block_falls_back_to_default(tmp_path):
    from pipeline.compute.registry import default_compute_config, load_compute_config

    # A real yaml file that simply has no ``compute:`` key.
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("paths:\n  content_root: /tmp/x\n", encoding="utf-8")
    cfg = load_compute_config(cfg_file)
    default = default_compute_config()
    for cap in Capability:
        assert cfg.backend_name_for(cap) == default.backend_name_for(cap)


# --------------------------------------------------------------------------- #
# Real adapters self-register on import.                                       #
# --------------------------------------------------------------------------- #
def test_adapters_self_register():
    import pipeline.compute  # noqa: F401 - triggers @register side effects

    assert is_registered("local_mps")
    assert is_registered("rented_metal")


def test_rented_metal_requires_base_url():
    from pipeline.compute.rented_metal import RentedMetalBackend

    with pytest.raises(ValueError):
        RentedMetalBackend(base_url="")


def test_rented_metal_health_unreachable_is_false_not_raise():
    from pipeline.compute.rented_metal import RentedMetalBackend

    # An unroutable URL: health() must report ok=False, never raise.
    backend = RentedMetalBackend(base_url="http://127.0.0.1:1", timeout=1)
    health = backend.health()
    assert health.ok is False


# --------------------------------------------------------------------------- #
# Guarded smoke test: LocalMPSBackend construction + capabilities.             #
# Construction is cheap (no weights); skip only if heavy deps to import even    #
# the wrapper are missing. Mirrors test_self_retrieval's skipif style.          #
# --------------------------------------------------------------------------- #
def test_local_mps_construction_and_capabilities():
    from pipeline.compute.local_mps import ALL_CAPABILITIES, LocalMPSBackend

    backend = LocalMPSBackend()
    assert backend.name == "local_mps"
    assert backend.mode == "realtime"
    assert backend.privacy == "local"
    assert backend.capabilities == ALL_CAPABILITIES
    assert backend.health().ok is True
    # No model is loaded by construction (lazy accessors are still None).
    assert backend._embedder is None  # noqa: SLF001 - asserting laziness


# NOTE: a real-weights LocalMPSBackend tag smoke (Tier-0 ONNX over a sample
# image) is a MANUAL, box-only check — it needs models/wd-eva02/model.onnx, which
# is not in the repo. There is intentionally no automated test here: a stub that
# always pytest.skip()s only inflates the skip count without ever asserting.
