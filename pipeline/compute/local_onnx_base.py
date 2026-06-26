"""Shared ONNX-Runtime backend base for the cross-platform ``local_*`` family.

``local_cuda`` / ``local_directml`` / ``local_cpu`` are identical except for the
ONNX Runtime **execution-provider** preference + their registry name, so the
real work lives here once. Each subclass sets ``EP_PREFERENCE`` (ordered, most
specific first); the base always appends ``CPUExecutionProvider`` as the
guaranteed fallback and filters to whatever ORT actually advertises on the host.

Capabilities (design §2 — ONNX is the primary CV path; the VLM stays torch/MLX):

  * TAG   (Tier 0) — WD-EVA02 + JoyTag ONNX, reusing ``tier0_tagger``'s pure
                     preprocess/postprocess helpers + our own EP-bound sessions.
  * EMBED (Tier 1) — the exported SigLIP **image tower** ONNX (1152-dim, then
                     L2-normalized), pure-numpy preprocessed (no transformers
                     at runtime). The export + parity check is
                     ``scripts/export_onnx.py``.
  * DETECT(Tier 3) — NudeNet (``NudeDetector`` accepts a ``providers`` list),
                     converted via ``tier3_nudenet.convert_regions``.
  * CAPTION(Tier 2)— delegated to ``Tier2Captioner`` (torch/MLX VLM, impractical
                     to ONNX-export at 8B) — host-agnostic, lazy-loaded.

HEAVY-IMPORT RULE: nothing heavy at module top. ``onnxruntime`` / ``numpy`` /
``PIL`` / the tier modules are imported lazily inside the methods, so importing
this module (and constructing a backend) is cheap on a box without the weights.
``privacy="local"`` / ``mode="realtime"`` for every subclass — pixels never leave
the box, so the dispatcher's privacy gate passes uncensored work by construction.
"""

from __future__ import annotations

from pathlib import Path
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
from pipeline.settings import get_settings

ALL_CAPABILITIES = {
    Capability.EMBED,
    Capability.TAG,
    Capability.CAPTION,
    Capability.DETECT,
}

# Model locations under settings.models_cache_dir — the SAME root the first-run
# weight pull writes to (audit P0-3). Box-only / gitignored. Resolved at import;
# a models-dir change needs a process restart.
_MODELS = get_settings().models_cache_dir
WD_MODEL_PATH = _MODELS / "wd-eva02" / "model.onnx"
JOYTAG_MODEL_PATH = _MODELS / "joytag" / "model.onnx"
# Produced by scripts/export_onnx.py (SigLIP SO400M image tower, 1152-dim out).
SIGLIP_ONNX_PATH = _MODELS / "siglip-image-tower" / "model.onnx"

SIGLIP_EMBEDDING_DIM = 1152
SIGLIP_MODEL_ID = "google/siglip-so400m-patch14-384"
SIGLIP_IMG_SIZE = 384


def siglip_preprocess(img: Any) -> Any:
    """SigLIP SO400M image preprocess -> float32 [1,3,384,384] (NCHW, RGB).

    Pure numpy/PIL replica of the transformers ``SiglipImageProcessor``: resize
    to 384x384 (bicubic), rescale to [0,1], normalize mean=0.5 std=0.5. Kept here
    so the ONNX embed path needs NO transformers at runtime. PARITY NOTE: SigLIP
    resizes (not pad-to-square) — matches the processor used by ``Tier1Embedder``.
    """
    import numpy as np
    from PIL import Image

    img = img.convert("RGB").resize((SIGLIP_IMG_SIZE, SIGLIP_IMG_SIZE), Image.BICUBIC)
    arr = np.asarray(img, dtype=np.float32) / 255.0  # HWC RGB 0..1
    arr = (arr - 0.5) / 0.5  # mean=0.5 std=0.5 -> [-1, 1]
    arr = np.transpose(arr, (2, 0, 1))  # HWC -> CHW
    return np.ascontiguousarray(arr, dtype=np.float32)[np.newaxis, ...]


class LocalONNXBackend:
    """ONNX-Runtime CV backend, EP chosen by the subclass. Local privacy.

    Subclasses set ``name`` and ``EP_PREFERENCE`` (an ordered list of ORT EP
    names). Construction is cheap — sessions/weights load lazily on first call.
    """

    mode: Mode = "realtime"
    privacy: Privacy = "local"
    # Ordered EP preference, most specific first. Subclass overrides this.
    EP_PREFERENCE: tuple[str, ...] = ("CPUExecutionProvider",)

    def __init__(self, name: str | None = None, **_: Any) -> None:
        # Extra config keys accepted + ignored (forward-compatible config blocks).
        self.name = name or getattr(type(self), "NAME", "local_onnx")
        self.capabilities: set[Capability] = set(ALL_CAPABILITIES)
        self._wd_session: Any = None
        self._joytag_session: Any = None
        self._siglip_session: Any = None
        self._detector: Any = None
        self._captioner: Any = None
        self._wd_labels: Any = None
        self._joytag_labels: Any = None

    # -- EP resolution --------------------------------------------------------
    def resolved_providers(self) -> list[str]:
        """The subclass EP preference, filtered to what ORT advertises here.

        Always guarantees ``CPUExecutionProvider`` as the final fallback so a
        session never fails to build for lack of the preferred accelerator.
        """
        import onnxruntime as ort

        avail = set(ort.get_available_providers())
        prefs = list(self.EP_PREFERENCE)
        if "CPUExecutionProvider" not in prefs:
            prefs.append("CPUExecutionProvider")
        use = [p for p in prefs if p in avail]
        return use or ["CPUExecutionProvider"]

    def _make_session(self, model_path: Path) -> Any:
        import onnxruntime as ort

        if not model_path.exists():
            raise FileNotFoundError(
                f"ONNX model not found at {model_path}. Weights are box-only "
                f"(gitignored); export/download them on the inference host."
            )
        providers = self.resolved_providers()
        # Disable TF32 on the CUDA EP for fp32 parity with the Mac CPU path
        # (TF32 matmuls shift logits ~0.3 and break Tier-0 tag parity — see
        # scripts/remote_pipeline_runner.py:_onnx_session).
        entries: list[Any] = [
            ("CUDAExecutionProvider", {"use_tf32": 0})
            if p == "CUDAExecutionProvider"
            else p
            for p in providers
        ]
        return ort.InferenceSession(str(model_path), providers=entries)

    # -- lazy session / label accessors --------------------------------------
    def _get_wd(self) -> Any:
        if self._wd_session is None:
            from pipeline.tier0_tagger import load_wd_labels

            self._wd_session = self._make_session(WD_MODEL_PATH)
            self._wd_labels = load_wd_labels()
        return self._wd_session

    def _get_joytag(self) -> Any:
        if self._joytag_session is None:
            from pipeline.tier0_tagger import load_joytag_labels

            self._joytag_session = self._make_session(JOYTAG_MODEL_PATH)
            self._joytag_labels = load_joytag_labels()
        return self._joytag_session

    def _get_siglip(self) -> Any:
        if self._siglip_session is None:
            self._siglip_session = self._make_session(SIGLIP_ONNX_PATH)
        return self._siglip_session

    def _get_detector(self) -> Any:
        if self._detector is None:
            from nudenet import NudeDetector

            # NudeDetector accepts the same EP list; CPU fallback is built in.
            self._detector = NudeDetector(providers=self.resolved_providers())
        return self._detector

    def _get_captioner(self) -> Any:
        if self._captioner is None:
            from pipeline.tier2_captioner import Tier2Captioner

            self._captioner = Tier2Captioner()
        return self._captioner

    # -- capabilities ---------------------------------------------------------
    def tag(self, refs: list[ImageRef]) -> list[TagSet]:
        from PIL import Image

        from pipeline.tier0_tagger import (
            joytag_preprocess as _joytag_pre,
        )
        from pipeline.tier0_tagger import (
            map_joytag_logits,
            map_wd_logits,
            wd_preprocess,
        )

        wd_sess = self._get_wd()
        joy_sess = self._get_joytag()
        wd_in = wd_sess.get_inputs()[0].name
        joy_in = joy_sess.get_inputs()[0].name

        out: list[TagSet] = []
        for ref in refs:
            with Image.open(ref.resolve()) as img:
                img = img.convert("RGB")
                wd_logits = wd_sess.run(None, {wd_in: wd_preprocess(img)})[0][0]
                joy_logits = joy_sess.run(None, {joy_in: _joytag_pre(img)})[0][0]
            wd_tags = map_wd_logits(wd_logits, self._wd_labels)
            joytag_tags = map_joytag_logits(joy_logits, self._joytag_labels)
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

    def embed(self, refs: list[ImageRef]) -> list[Vector]:
        import numpy as np
        from PIL import Image

        sess = self._get_siglip()
        in_name = sess.get_inputs()[0].name
        out: list[Vector] = []
        for ref in refs:
            with Image.open(ref.resolve()) as img:
                x = siglip_preprocess(img)
            pooled = np.asarray(sess.run(None, {in_name: x})[0][0], dtype=np.float32)
            norm = float(np.linalg.norm(pooled)) or 1.0
            vec = (pooled / norm).astype(np.float32)
            out.append(
                Vector(
                    image_id=ref.image_id,
                    values=vec.tolist(),
                    dim=int(vec.shape[0]),
                    model=SIGLIP_MODEL_ID,
                )
            )
        return out

    def detect(self, refs: list[ImageRef]) -> list[Regions]:
        from pipeline.tier3_nudenet import convert_regions

        detector = self._get_detector()
        return [
            Regions(
                image_id=ref.image_id,
                regions=convert_regions(detector.detect(str(ref.resolve()))),
            )
            for ref in refs
        ]

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

    # -- health / cost --------------------------------------------------------
    def health(self) -> Health:
        """Report the resolved EP set; never loads weights (cheap probe)."""
        try:
            providers = self.resolved_providers()
        except Exception as exc:  # noqa: BLE001 - ORT missing -> report, don't raise
            return Health(ok=False, detail=f"onnxruntime unavailable: {exc}")
        return Health(ok=True, detail=f"{self.name} EPs={providers}")

    def cost_estimate(self, n: int, cap: Capability) -> CostEstimate:
        return CostEstimate(
            usd=0.0, n=n, capability=cap, detail="local (no marginal $)"
        )
