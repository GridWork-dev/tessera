"""Tier 0 structured tagger: WD-EVA02 + JoyTag (ONNX, multi-label).

Two ONNX tag models run on every image and produce scored, structured tags:

- WD-EVA02 (SmilingWolf) -- ``models/wd-eva02/model.onnx`` [N,448,448,3] NHWC,
  BGR float32 0..255 (model normalizes internally), 10861 probabilities (sigmoid
  is in-graph -- do NOT sigmoid the output). Labels live in
  ``selected_tags.csv`` (category 0=general -> ``tags``, 4=character -> ``person``,
  9=rating -> ``rating`` via argmax of the 4 rating logits). tag_source ``wd_eva02``.
- JoyTag -- ``models/joytag/model.onnx`` [N,3,448,448] NCHW, RGB CLIP-normalized,
  5813 logits. Labels in ``top_tags.txt`` (read with ``.read().splitlines()``).
  general tags -> ``tags``. tag_source ``joytag``.

HEAVY-IMPORT RULE: numpy / onnxruntime / PIL are safe at module top (present on
the MacBook gate). The ``.onnx`` weights are box-only/gitignored, so the pure
preprocessing + label-mapping functions never require them -- only
``_session()`` loads a model and that happens lazily on first use.

The big ``.onnx`` files are NOT in the repo; the small label files
(``selected_tags.csv``, ``top_tags.txt``) ARE, so this module imports and the
unit tests run on the MacBook without the weights.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from pipeline.paths import resolve_image_path
from pipeline.settings import get_settings

# ---------------------------------------------------------------------------
# Model + label locations under settings.models_cache_dir — the SAME root the
# first-run weight pull writes to (audit P0-3). .onnx are box-only / gitignored.
# Resolved at import; a models-dir change needs a process restart.
# ---------------------------------------------------------------------------
_MODELS = get_settings().models_cache_dir
WD_MODEL_PATH = _MODELS / "wd-eva02" / "model.onnx"
WD_LABELS_PATH = _MODELS / "wd-eva02" / "selected_tags.csv"
JOYTAG_MODEL_PATH = _MODELS / "joytag" / "model.onnx"
JOYTAG_LABELS_PATH = _MODELS / "joytag" / "top_tags.txt"

# Image size shared by both models.
IMG_SIZE = 448

# WD-EVA02 expected output width (sanity check / documentation).
WD_NUM_TAGS = 10861
# JoyTag expected output width.
JOYTAG_NUM_TAGS = 5813

# WD-EVA02 SmilingWolf category integers (selected_tags.csv `category` column).
WD_CAT_GENERAL = 0
WD_CAT_CHARACTER = 4
WD_CAT_RATING = 9

# Map WD categories -> repo tag categories.
WD_CATEGORY_MAP = {
    WD_CAT_GENERAL: "tags",
    WD_CAT_CHARACTER: "person",
    WD_CAT_RATING: "rating",
}

# Thresholds (ground truth from the box).
# WD general floor raised 0.35 -> 0.45 (locked decision 2026-06-23): the
# 0.35-0.45 band was noisy junk. JoyTag (0.40) + WD character (0.85) unchanged.
WD_GENERAL_THRESHOLD = 0.45
WD_CHARACTER_THRESHOLD = 0.85
JOYTAG_THRESHOLD = 0.40

# CLIP normalization for JoyTag.
CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)


# ---------------------------------------------------------------------------
# Pure helpers (no .onnx required)
# ---------------------------------------------------------------------------
def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _pad_to_square(img: Image.Image, fill: tuple[int, int, int]) -> Image.Image:
    """Pad a PIL RGB image to a centered square on a solid background."""
    w, h = img.size
    side = max(w, h)
    if w == side and h == side:
        return img
    canvas = Image.new("RGB", (side, side), fill)
    canvas.paste(img, ((side - w) // 2, (side - h) // 2))
    return canvas


def wd_preprocess(img: Image.Image) -> np.ndarray:
    """WD-EVA02 preprocess -> float32 array shape [1,448,448,3] (NHWC, BGR, 0..255).

    PIL RGB -> pad to square with WHITE -> resize 448 -> RGB->BGR ->
    float32 0..255 (NO /255, NO mean/std; the model normalizes internally).
    """
    img = img.convert("RGB")
    img = _pad_to_square(img, (255, 255, 255))
    img = img.resize((IMG_SIZE, IMG_SIZE), Image.BICUBIC)
    arr = np.asarray(img, dtype=np.float32)  # HWC, RGB, 0..255
    arr = arr[:, :, ::-1]  # RGB -> BGR
    arr = np.ascontiguousarray(arr)
    return arr[np.newaxis, ...]  # [1,448,448,3]


def joytag_preprocess(img: Image.Image) -> np.ndarray:
    """JoyTag preprocess -> float32 array shape [1,3,448,448] (NCHW, RGB, CLIP-norm).

    PIL RGB -> pad to square -> resize 448 -> scale [0,1] -> CLIP mean/std ->
    NCHW.
    """
    img = img.convert("RGB")
    img = _pad_to_square(img, (255, 255, 255))
    img = img.resize((IMG_SIZE, IMG_SIZE), Image.BICUBIC)
    arr = np.asarray(img, dtype=np.float32) / 255.0  # HWC, RGB, 0..1
    arr = (arr - CLIP_MEAN) / CLIP_STD
    arr = np.transpose(arr, (2, 0, 1))  # HWC -> CHW
    arr = np.ascontiguousarray(arr, dtype=np.float32)
    return arr[np.newaxis, ...]  # [1,3,448,448]


def load_wd_labels(csv_path: Path | str = WD_LABELS_PATH) -> dict[str, list]:
    """Parse selected_tags.csv -> label/category lists, index == logit index.

    Returns a dict with:
      - ``names``: list[str] of every tag name (len 10861), row order preserved.
      - ``categories``: list[int] parallel to ``names`` (0/4/9).
      - ``rating_indices``: list[int] of the 4 rating-row logit indices, in order.
      - ``rating_names``: list[str] parallel to ``rating_indices``.
    """
    names: list[str] = []
    categories: list[int] = []
    rating_indices: list[int] = []
    rating_names: list[str] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)  # tag_id,name,category,count
        name_col = header.index("name")
        cat_col = header.index("category")
        for idx, row in enumerate(reader):
            name = row[name_col]
            cat = int(row[cat_col])
            names.append(name)
            categories.append(cat)
            if cat == WD_CAT_RATING:
                rating_indices.append(idx)
                rating_names.append(name)
    return {
        "names": names,
        "categories": categories,
        "rating_indices": rating_indices,
        "rating_names": rating_names,
    }


def load_joytag_labels(txt_path: Path | str = JOYTAG_LABELS_PATH) -> list[str]:
    """Read top_tags.txt with .read().splitlines() -> 5813 tags (index==logit)."""
    with open(txt_path, encoding="utf-8") as f:
        return f.read().splitlines()


def map_wd_logits(
    logits: np.ndarray,
    labels: dict[str, list] | None = None,
    *,
    general_threshold: float = WD_GENERAL_THRESHOLD,
    character_threshold: float = WD_CHARACTER_THRESHOLD,
) -> list[tuple[str, str, float]]:
    """WD-EVA02 outputs -> scored tags as ``[(category, value, score), ...]``.

    WD-EVA02 emits probabilities directly (sigmoid is in-graph), so the
    ``logits`` argument is already in [0, 1] and is used as-is -- NO sigmoid:
      - general (cat 0, prob >= general_threshold) -> category ``tags``
      - character (cat 4, prob >= character_threshold) -> category ``person``
      - rating (cat 9) -> single tag = argmax over the 4 rating probs ->
        category ``rating``
    """
    if labels is None:
        labels = load_wd_labels()
    # WD-EVA02 ONNX applies sigmoid IN-GRAPH -> the output is ALREADY
    # probabilities in [0, 1]. Do NOT sigmoid again: doing so squashes every
    # value into [0.5, 0.73] and fires ~99% of the 10861 tags. (JoyTag, by
    # contrast, emits raw logits and DOES need _sigmoid -- see map_joytag_logits.)
    probs = np.asarray(logits, dtype=np.float32).reshape(-1)
    names = labels["names"]
    cats = labels["categories"]

    out: list[tuple[str, str, float]] = []
    for idx, prob in enumerate(probs):
        cat = cats[idx]
        if cat == WD_CAT_GENERAL and prob >= general_threshold:
            out.append(("tags", names[idx], float(prob)))
        elif cat == WD_CAT_CHARACTER and prob >= character_threshold:
            out.append(("person", names[idx], float(prob)))

    rating_indices = labels["rating_indices"]
    if rating_indices:
        rating_probs = probs[rating_indices]
        best = int(np.argmax(rating_probs))
        best_idx = rating_indices[best]
        out.append(("rating", names[best_idx], float(probs[best_idx])))
    return out


def map_joytag_logits(
    logits: np.ndarray,
    labels: list[str],
    *,
    threshold: float = JOYTAG_THRESHOLD,
) -> list[tuple[str, float]]:
    """JoyTag logits -> ``[(value, score), ...]`` for tags >= threshold (sigmoid)."""
    logits = np.asarray(logits, dtype=np.float32).reshape(-1)
    probs = _sigmoid(logits)
    out: list[tuple[str, float]] = []
    for idx, prob in enumerate(probs):
        if prob >= threshold:
            out.append((labels[idx], float(prob)))
    return out


# ---------------------------------------------------------------------------
# Tagger (loads ONNX sessions lazily)
# ---------------------------------------------------------------------------
class Tier0Tagger:
    """Runs WD-EVA02 + JoyTag and writes scored, structured tags.

    ONNX sessions load lazily on first ``tag_image`` call so the module imports
    on a machine without the weights. Label files are loaded eagerly (they ship
    in the repo).
    """

    def __init__(
        self,
        wd_model_path: Path | str = WD_MODEL_PATH,
        joytag_model_path: Path | str = JOYTAG_MODEL_PATH,
        wd_labels_path: Path | str = WD_LABELS_PATH,
        joytag_labels_path: Path | str = JOYTAG_LABELS_PATH,
    ) -> None:
        self.wd_model_path = Path(wd_model_path)
        self.joytag_model_path = Path(joytag_model_path)
        self.wd_labels = load_wd_labels(wd_labels_path)
        self.joytag_labels = load_joytag_labels(joytag_labels_path)
        self._wd_session: ort.InferenceSession | None = None
        self._joytag_session: ort.InferenceSession | None = None

    # -- session loading -----------------------------------------------------
    @staticmethod
    def _load_session(path: Path) -> ort.InferenceSession:
        if not path.exists():
            raise FileNotFoundError(
                f"ONNX model not found at {path}. Tier 0 weights are box-only "
                f"(gitignored, ~1.2GB WD / ~349MB JoyTag) and must be present "
                f"on the inference host to run inference."
            )
        return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])

    @property
    def wd_session(self) -> ort.InferenceSession:
        if self._wd_session is None:
            self._wd_session = self._load_session(self.wd_model_path)
        return self._wd_session

    @property
    def joytag_session(self) -> ort.InferenceSession:
        if self._joytag_session is None:
            self._joytag_session = self._load_session(self.joytag_model_path)
        return self._joytag_session

    # -- inference -----------------------------------------------------------
    def _run_wd(self, img: Image.Image) -> list[tuple[str, str, float]]:
        x = wd_preprocess(img)
        sess = self.wd_session
        in_name = sess.get_inputs()[0].name
        logits = sess.run(None, {in_name: x})[0][0]
        return map_wd_logits(logits, self.wd_labels)

    def _run_joytag(self, img: Image.Image) -> list[tuple[str, float]]:
        x = joytag_preprocess(img)
        sess = self.joytag_session
        in_name = sess.get_inputs()[0].name
        logits = sess.run(None, {in_name: x})[0][0]
        return map_joytag_logits(logits, self.joytag_labels)

    def tag_image(self, rel_path: str, session, image_id: int, db) -> list[dict]:
        """Tag one image and persist scored rows via ``db.add_tags_scored``.

        ``rel_path`` is RELATIVE to the content root (resolved via
        ``resolve_image_path``). Runs both models, builds scored rows, and writes
        them with explicit per-tag ``tag_source`` + ``confidence`` through
        ``Database.add_tags_scored`` (added by the Integrate phase).

        Returns the rows that were written.
        """
        abs_path = resolve_image_path(rel_path)
        with Image.open(abs_path) as img:
            img = img.convert("RGB")
            wd_tags = self._run_wd(img)
            joytag_tags = self._run_joytag(img)

        rows: list[dict] = []
        for category, value, score in wd_tags:
            rows.append(
                {
                    "category": category,
                    "value": value,
                    "confidence": score,
                    "tag_source": "wd_eva02",
                }
            )
        for value, score in joytag_tags:
            rows.append(
                {
                    "category": "tags",
                    "value": value,
                    "confidence": score,
                    "tag_source": "joytag",
                }
            )

        db.add_tags_scored(session, image_id, rows)
        return rows
