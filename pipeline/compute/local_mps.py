"""Local MPS backend — wraps the existing Tier 0-3 modules.

This is the adapter that has always run on the Mac mini: it delegates to the
real tier classes (``Tier1Embedder``, ``Tier0Tagger``, ``Tier2Captioner``,
``Tier3NudeNet``) rather than reimplementing inference. It advertises all four
capabilities, runs in ``realtime`` mode, and is ``local`` privacy (pixels never
leave the box).

HEAVY-IMPORT RULE (same as the tier modules): the tier classes lazy-load torch /
transformers / onnxruntime / nudenet on first use, so importing THIS module is
cheap and safe on a machine without the weights. We mirror that: the tier
classes are imported lazily inside ``_*`` accessors, never at module top.
"""

from __future__ import annotations

from typing import Any

from pipeline.compute.base import (
    Capability,
    Caption,
    CostEstimate,
    Health,
    ImageRef,
    Mode,
    Privacy,
    Regions,
    TagSet,
    Vector,
)
from pipeline.compute.registry import register

ALL_CAPABILITIES = {
    Capability.EMBED,
    Capability.TAG,
    Capability.CAPTION,
    Capability.DETECT,
}


@register("local_mps")
class LocalMPSBackend:
    """All four capabilities, delegated to the on-box tier modules.

    Construction is cheap (no models loaded); the wrapped tier classes load
    their heavy deps lazily on first inference call, matching the existing
    ``batch_tag.py`` behavior.
    """

    mode: Mode = "realtime"
    privacy: Privacy = "local"

    def __init__(self, name: str = "local_mps", **_: Any) -> None:
        # Extra config keys are accepted and ignored so the same config block
        # tolerates forward-compatible additions without breaking construction.
        self.name = name
        self.capabilities: set[Capability] = set(ALL_CAPABILITIES)
        self._embedder: Any = None
        self._tagger: Any = None
        self._captioner: Any = None
        self._detector: Any = None

    # -- lazy tier accessors (heavy imports happen here, not at module top) ---
    def _get_embedder(self) -> Any:
        if self._embedder is None:
            from pipeline.tier1_embedder import Tier1Embedder

            self._embedder = Tier1Embedder()
        return self._embedder

    def _get_tagger(self) -> Any:
        if self._tagger is None:
            from pipeline.tier0_tagger import Tier0Tagger

            self._tagger = Tier0Tagger()
        return self._tagger

    def _get_captioner(self) -> Any:
        if self._captioner is None:
            from pipeline.tier2_captioner import Tier2Captioner

            self._captioner = Tier2Captioner()
        return self._captioner

    def _get_detector(self) -> Any:
        if self._detector is None:
            from pipeline.tier3_nudenet import Tier3NudeNet

            self._detector = Tier3NudeNet()
        return self._detector

    # -- capabilities ---------------------------------------------------------
    def embed(self, refs: list[ImageRef]) -> list[Vector]:
        embedder = self._get_embedder()
        rel_paths = [r.rel_path for r in refs]
        mat = embedder.embed_images_batched(rel_paths)
        dim = embedder.EMBEDDING_DIM
        return [
            Vector(
                image_id=ref.image_id,
                values=row.astype(float).tolist(),
                dim=dim,
                model=embedder.MODEL_ID,
            )
            for ref, row in zip(refs, mat)
        ]

    def tag(self, refs: list[ImageRef]) -> list[TagSet]:
        from PIL import Image

        tagger = self._get_tagger()
        out: list[TagSet] = []
        for ref in refs:
            with Image.open(ref.resolve()) as img:
                img = img.convert("RGB")
                # Delegate to the tier's own model runs (same as tier0_tagger);
                # we only reshape the scored tuples into TagSet rows here.
                wd_tags = tagger._run_wd(img)  # noqa: SLF001 - reuse tier inference
                joytag_tags = tagger._run_joytag(img)  # noqa: SLF001
            rows: list[dict[str, Any]] = [
                {
                    "category": category,
                    "value": value,
                    "confidence": score,
                    "tag_source": "wd_eva02",
                }
                for category, value, score in wd_tags
            ]
            rows.extend(
                {
                    "category": "tags",
                    "value": value,
                    "confidence": score,
                    "tag_source": "joytag",
                }
                for value, score in joytag_tags
            )
            out.append(TagSet(image_id=ref.image_id, tags=rows))
        return out

    def caption(self, refs: list[ImageRef]) -> list[Caption]:
        captioner = self._get_captioner()
        return [
            Caption(
                image_id=ref.image_id,
                text=captioner.caption_image(ref.rel_path),
                model=captioner.model,
            )
            for ref in refs
        ]

    def detect(self, refs: list[ImageRef]) -> list[Regions]:
        detector = self._get_detector()
        return [
            Regions(
                image_id=ref.image_id,
                regions=detector.detect_image(ref.rel_path),
            )
            for ref in refs
        ]

    # -- health / cost --------------------------------------------------------
    def health(self) -> Health:
        """Local compute is always reachable; only ``caption`` has a server.

        We don't probe the mlx caption server here (that would force a network
        call on every health check); construction-only health keeps the seam
        cheap. The captioner exposes its own ``health()`` for the caption path.
        """
        return Health(ok=True, detail="local MPS tiers (lazy-loaded)")

    def cost_estimate(self, n: int, cap: Capability) -> CostEstimate:
        # Local compute is free at the margin (electricity aside).
        return CostEstimate(
            usd=0.0, n=n, capability=cap, detail="local (no marginal $)"
        )
