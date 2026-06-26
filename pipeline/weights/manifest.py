"""Model-weights manifest — what the pipeline needs, where it comes from, how big.

The pipeline does NOT bundle multi-GB weights in the installer (Spec E): the
artifact stays small and weights are pulled on first run. This manifest is the
single source of truth for that pull — every model the tiers load, with its
source, on-disk destination, approximate size, license, and whether it is
required for the app to function or an opt-in extra.

Three delivery shapes (``ModelSpec.source``):

* ``hf``   — a HuggingFace repo. Either snapshotted whole into the relocatable
             HF cache (``files is None``; what ``transformers.from_pretrained``
             reads), or specific ``files`` downloaded into a local ``dest`` dir
             (the ONNX taggers the pipeline mmaps directly).
* ``url``  — a plain HTTP(S) download into ``dest`` (e.g. the OpenCV-Zoo SFace
             ONNX, which is not on the Hub).
* ``lib``  — fetched by a third-party library on first use (NudeNet's
             ``NudeDetector()`` self-downloads its ONNX). We can't pre-place it,
             only flag it.

Sizes are APPROXIMATE (preview only — the authoritative size is whatever the
Hub reports at pull time). Licenses are best-known as of 2026-06; verify against
the live model card before redistributing anything. NudeNet is AGPL-3.0, so it
is NEVER pulled unless the user explicitly opts in (``--include-nudenet``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    """One model the pipeline can load, and how to deliver its weights."""

    key: str  # stable id used by CLI/API
    title: str  # human label
    purpose: str  # which tier / feature it powers
    source: str  # "hf" | "url" | "lib"
    approx_size_mb: int  # preview estimate only
    license: str
    required: bool  # True == app is non-functional without it
    # hf: repo to pull from. url: ignored. lib: ignored.
    repo_id: str | None = None
    # hf: specific files -> local dest dir; None == snapshot whole repo into the
    # HF cache. url: the single file's URL.
    files: tuple[str, ...] | None = None
    url: str | None = None
    # Relative (to models_root) destination dir for source in {hf-with-files, url}.
    dest: str | None = None
    gated: bool = False  # needs an HF token / license click-through
    opt_in: bool = False  # never auto-pulled (AGPL etc.) — explicit flag required
    notes: str = ""


# --- the real inventory (model ids/paths verified against the codebase) --------

MANIFEST: tuple[ModelSpec, ...] = (
    ModelSpec(
        key="siglip",
        title="SigLIP SO400M (patch14-384)",
        purpose="Tier 1 — image+text embeddings (semantic search, find-similar)",
        source="hf",
        repo_id="google/siglip-so400m-patch14-384",
        approx_size_mb=1700,
        license="Apache-2.0",
        required=True,
        notes="Image and text towers MUST match. siglip2 variant is the upgrade "
        "path (scripts/reembed_siglip2.py) and is pulled only during a re-embed.",
    ),
    ModelSpec(
        key="wd-eva02",
        title="WD EVA02-Large Tagger v3",
        purpose="Tier 0 — structured tags",
        source="hf",
        repo_id="SmilingWolf/wd-eva02-large-tagger-v3",
        files=("model.onnx", "selected_tags.csv"),
        dest="wd-eva02",
        approx_size_mb=1200,
        license="Apache-2.0",
        required=True,
    ),
    ModelSpec(
        key="joytag",
        title="JoyTag",
        purpose="Tier 0 — structured tags",
        source="hf",
        repo_id="fancyfeast/joytag",
        files=("model.onnx", "top_tags.txt"),
        dest="joytag",
        approx_size_mb=660,
        license="Apache-2.0",
        required=True,
    ),
    ModelSpec(
        key="joycaption",
        title="JoyCaption Beta One (LLaVA)",
        purpose="Tier 2 — free-text captions",
        source="hf",
        repo_id="fancyfeast/llama-joycaption-beta-one-hf-llava",
        approx_size_mb=17000,
        # Llama/LLaVA-derived: the wrapper is permissive but the base may add
        # terms — verify the model card's license before redistributing.
        license="Apache-2.0 (wrapper; base = Llama/LLaVA — verify)",
        required=False,
        gated=False,  # confirmed ungated 2026-06 (no token needed)
        notes="Large (~17 GB). Optional — only needed for captioning.",
    ),
    ModelSpec(
        key="nsfw2mini",
        title="NSFW-Detection-2-Mini (EfficientNet-b4)",
        purpose="Optional rating reclassifier (approval-gated)",
        source="hf",
        repo_id="viddexa/nsfw-detection-2-mini",
        approx_size_mb=75,
        license="unverified — see model card",
        required=False,
        opt_in=True,  # redistributability unverified -> never in the default pull set
    ),
    ModelSpec(
        key="sface",
        title="SFace face-recognition (OpenCV Zoo)",
        purpose="Faces — 128-dim embeddings (commercial-safe default)",
        source="url",
        url=(
            "https://github.com/opencv/opencv_zoo/raw/main/models/"
            "face_recognition_sface/face_recognition_sface_2021dec.onnx"
        ),
        dest="face",
        approx_size_mb=37,
        license="Apache-2.0",
        required=False,
    ),
    ModelSpec(
        key="whisper-base",
        title="faster-whisper base",
        purpose="Deep video — scene transcripts",
        source="hf",
        repo_id="Systran/faster-whisper-base",
        approx_size_mb=145,
        license="MIT",
        required=False,
    ),
    ModelSpec(
        key="nudenet",
        title="NudeNet detector",
        purpose="Tier 3 — region metadata (never a gate)",
        source="lib",
        approx_size_mb=90,
        license="AGPL-3.0",
        required=False,
        opt_in=True,
        notes="AGPL — pulled by the nudenet package on first NudeDetector(); only "
        "fetched when the user explicitly opts in. Region metadata only.",
    ),
)


# --- queries -------------------------------------------------------------------


def by_key(key: str) -> ModelSpec:
    for spec in MANIFEST:
        if spec.key == key:
            return spec
    raise KeyError(f"unknown model {key!r}; known: {[s.key for s in MANIFEST]}")


def selected(
    *, include_optional: bool = True, include_opt_in: bool = False
) -> list[ModelSpec]:
    """The models a given pull would touch.

    Required models always included. Optional (non-opt-in) included unless
    ``include_optional`` is False. opt-in models (NudeNet/AGPL) included only
    when ``include_opt_in`` is True.
    """
    out: list[ModelSpec] = []
    for spec in MANIFEST:
        if spec.opt_in:
            if include_opt_in:
                out.append(spec)
        elif spec.required or include_optional:
            out.append(spec)
    return out


def total_size_mb(
    specs: list[ModelSpec] | None = None,
    *,
    include_optional: bool = True,
    include_opt_in: bool = False,
) -> int:
    """Approximate total download size (MB) for a selection."""
    if specs is None:
        specs = selected(
            include_optional=include_optional, include_opt_in=include_opt_in
        )
    return sum(s.approx_size_mb for s in specs)
