"""
nsfw-2-mini rating classifier — a NEW rating signal (Wave-1 step 3).

Wraps ``viddexa/nsfw-detection-2-mini`` (Apache-2.0, ~17M params, CPU-friendly,
~96% macro F1 on LSPD) to produce a schema rating label. The published weights
are an **EfficientNet-b4** image-classifier exposed through the standard HF
``AutoModelForImageClassification`` API — NOT a SigLIP2 head (the master spec's
"SigLIP2-based" label is inaccurate; we target the real API). It classifies an
image into one of five classes — verified from the published weights as
``{0: safe, 1: hentai, 2: porn, 3: sexy, 4: drawing}`` (the benign class is
``safe``, NOT ``Normal`` as the model card prose implies) — read live from
``model.config.id2label`` (never hard-coded into inference).

This module is ADDITIVE and stands ALONGSIDE the existing Tier-0 rating path
(``pipeline/tag_runner.py::derive_rating``, which maps the WD-EVA02 rating head).
It does NOT edit that code and does NOT write ``images.rating``. Swapping the
rating *signal* from the WD head to this classifier is a deliberate central
wiring change (a corpus-wide behavior change), left to the orchestrator. NudeNet
*region* metadata (``images.nudenet_regions``) is unaffected — only the rating
role would move.

Heavy deps (torch / transformers) are imported lazily in ``_load`` — the MacBook
venv may lack them, so the module imports cleanly and its pure mapping tests run
without a model. numpy / PIL / paths are safe at module top.
"""

from __future__ import annotations

import logging
from typing import Any

from PIL import Image as PILImage

from pipeline.paths import resolve_image_path

logger = logging.getLogger(__name__)

MODEL_ID = "viddexa/nsfw-detection-2-mini"

# nsfw-2-mini class -> schema rating (unrated|sfw|suggestive|nsfw).
# Conservative, errs toward flagging (mirrors tag_runner.WD_RATING_TO_SCHEMA's
# intent): explicit photo/drawing -> nsfw, suggestive -> suggestive, clean -> sfw.
# Keys are LOWERCASED so lookup is case-insensitive (the model card capitalizes).
# The benign class in the published weights is ``safe`` (verified from
# id2label); ``normal`` is kept as a defensive alias for the model-card prose.
#   safe    : photos with no nsfw content                 -> sfw
#   drawing : comics/cartoons/drawings with no nsfw       -> sfw
#   sexy    : suggestive nudity / risqué clothing         -> suggestive
#   porn    : pornographic content                        -> nsfw
#   hentai  : drawings with sexual content                -> nsfw
LABEL_TO_RATING: dict[str, str] = {
    "safe": "sfw",
    "normal": "sfw",  # alias: model-card prose says "Normal"; weights emit "safe"
    "drawing": "sfw",
    "sexy": "suggestive",
    "porn": "nsfw",
    "hentai": "nsfw",
}


def derive_rating_from_label(label: str | None) -> str:
    """Map one nsfw-2-mini class label to the schema rating. PURE.

    Unknown / missing labels map to ``"unrated"`` (never guess a rating). Case
    and surrounding whitespace are normalized, so ``"Porn"`` and ``" porn "``
    both resolve.
    """
    key = (label or "").strip().lower()
    return LABEL_TO_RATING.get(key, "unrated")


def derive_rating_from_probs(probs: dict[str, float]) -> str:
    """Argmax over a {class: prob} map, then map to the schema rating. PURE.

    ``probs`` is the shape the ``moderators`` library / a transformers softmax
    yields. An empty map -> ``"unrated"`` (no signal to act on).
    """
    if not probs:
        return "unrated"
    top_label = max(probs, key=lambda k: probs[k])
    return derive_rating_from_label(top_label)


class Nsfw2MiniClassifier:
    """``viddexa/nsfw-detection-2-mini`` -> {class: prob} / schema rating.

    Torch + transformers are imported lazily in ``_load`` — the module imports
    cleanly on a box without them, matching the tier modules' contract. The
    model runs fine on CPU (it is ~17M params), so no MPS/GPU is required.
    """

    MODEL_ID = MODEL_ID

    def __init__(self) -> None:
        self.processor: Any = None
        self.model: Any = None
        self.device: Any = None
        self.id2label: dict[int, str] = {}

    def _load(self) -> None:
        """Lazily import torch + transformers and load the classifier (CPU-ok)."""
        if self.model is not None:
            return
        import torch  # lazy: MacBook venv may have no torch
        from transformers import AutoImageProcessor, AutoModelForImageClassification

        self.device = (
            torch.device("mps")
            if torch.backends.mps.is_available()
            else torch.device("cpu")
        )
        logger.info("Loading %s on %s ...", self.MODEL_ID, self.device)
        # use_fast=False: the model card pins the slow image processor.
        self.processor = AutoImageProcessor.from_pretrained(
            self.MODEL_ID, use_fast=False
        )
        self.model = (
            AutoModelForImageClassification.from_pretrained(self.MODEL_ID)
            .to(self.device)
            .eval()
        )
        # id2label keys come back as ints (or int-like strings) — normalize.
        self.id2label = {int(k): v for k, v in self.model.config.id2label.items()}

    def classify(self, rel_path: str) -> dict[str, float]:
        """Classify one image (DB-relative path) -> {class_label: probability}.

        Resolves the path via ``resolve_image_path`` (paths are RELATIVE to the
        content root) and returns a softmax over ``model.config.id2label``.
        """
        import torch  # lazy

        self._load()
        path = resolve_image_path(rel_path)
        with PILImage.open(path) as raw:
            img = raw.convert("RGB")
            inputs = self.processor(images=img, return_tensors="pt").to(self.device)
        with torch.no_grad():
            logits = self.model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)[0]
        return {self.id2label[i]: float(probs[i]) for i in range(probs.shape[0])}

    def rating_for(self, rel_path: str) -> str:
        """Classify one image and map its top class to the schema rating."""
        return derive_rating_from_probs(self.classify(rel_path))
