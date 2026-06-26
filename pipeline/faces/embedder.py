"""Face embedding — pluggable, commercial-safe-by-default.

Default = **SFace** (OpenCV ``face_recognition_sface``, ONNX via onnxruntime,
**Apache-2.0, 128-dim**) — commercial-safe, the shippable build's choice.
**ArcFace / buffalo_l** (512-dim) is selectable for private use but is
**FLAGGED NON-COMMERCIAL** (``license_commercial=False``): its weights are
research/non-commercial only.

Both load an ONNX model from a configured path and raise ``EmbedderUnavailable``
if onnxruntime or the model file is missing — callers (and tests) skip
gracefully. Output vectors are L2-normalized float32. The ``embedder`` name is
stored on each face row so a mixed store never silently compares across
embedders (clustering partitions by embedder).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

from pipeline.faces.detector import DetectedFace


class EmbedderUnavailable(RuntimeError):
    """Raised when an embedder's runtime dependency (onnxruntime/model) is missing."""


@runtime_checkable
class FaceEmbedder(Protocol):
    """Embed aligned face crops into L2-normalized vectors. On-box only."""

    name: str
    dim: int
    license_commercial: bool

    def embed(
        self, image_path: Path, faces: list[DetectedFace]
    ) -> list[np.ndarray]: ...


def l2_normalize(v: np.ndarray) -> np.ndarray:
    """L2-normalize a vector; zero-vector passes through unchanged."""
    n = float(np.linalg.norm(v))
    if n == 0.0:
        return v.astype(np.float32)
    return (v / n).astype(np.float32)


def _crop_normalized(img: np.ndarray, bbox: list[float], size: int) -> np.ndarray:
    """Crop a normalized [x,y,w,h] box from an HxWxC array, resize to size×size.

    Uses cv2 if available (best), else a nearest-neighbour numpy resize so the
    module stays importable without OpenCV for the pure-logic paths.
    """
    h, w = img.shape[:2]
    x0 = max(0, int(bbox[0] * w))
    y0 = max(0, int(bbox[1] * h))
    x1 = min(w, int((bbox[0] + bbox[2]) * w))
    y1 = min(h, int((bbox[1] + bbox[3]) * h))
    if x1 <= x0 or y1 <= y0:
        crop = img
    else:
        crop = img[y0:y1, x0:x1]
    try:
        import cv2

        return cv2.resize(crop, (size, size), interpolation=cv2.INTER_LINEAR)
    except Exception:
        ys = (np.linspace(0, crop.shape[0] - 1, size)).astype(int)
        xs = (np.linspace(0, crop.shape[1] - 1, size)).astype(int)
        return crop[np.ix_(ys, xs)]


# Canonical ArcFace/SFace 5-point template for a 112×112 aligned crop, in the
# order [left_eye, right_eye, nose, left_mouth, right_mouth]. SFace was trained on
# crops aligned to these points; feeding a raw bbox crop (no alignment) collapses
# distinct identities (the documented under-segmentation). Source: InsightFace.
_ARCFACE_TEMPLATE_112 = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)

# landmarks dict key carrying the 5 alignment points as normalized [x,y] pairs
# (top-left origin), ordered like _ARCFACE_TEMPLATE_112. Set by the detector.
LANDMARKS_POINTS5_KEY = "points5"


def _template_for_size(size: int) -> np.ndarray:
    """Scale the 112-px template to an arbitrary square output size."""
    return _ARCFACE_TEMPLATE_112 * (size / 112.0)


def _align_5point(
    img: np.ndarray, points5_norm: list[list[float]], size: int
) -> np.ndarray | None:
    """Similarity-warp a face to the canonical template via its 5 landmarks.

    ``points5_norm`` are normalized [x,y] (top-left origin) in template order.
    Returns a size×size aligned crop, or ``None`` if cv2 is unavailable or the
    transform cannot be estimated (caller falls back to a bbox crop).
    """
    try:
        import cv2
    except Exception:
        return None
    h, w = img.shape[:2]
    src = np.array([[p[0] * w, p[1] * h] for p in points5_norm], dtype=np.float32)
    dst = _template_for_size(size)
    m, _ = cv2.estimateAffinePartial2D(src, dst, method=cv2.LMEDS)
    if m is None:
        return None
    return cv2.warpAffine(img, m, (size, size), flags=cv2.INTER_LINEAR)


class _OnnxFaceEmbedder:
    """Shared ONNX runner: load a single-input recognition model, run NCHW crops."""

    name = "onnx"
    dim = 0
    license_commercial = True
    _input_size = 112

    def __init__(self, model_path: str | Path) -> None:
        try:
            import onnxruntime as ort
        except (
            Exception
        ) as exc:  # pragma: no cover - exercised only without onnxruntime
            raise EmbedderUnavailable("onnxruntime not importable") from exc
        mp = Path(model_path)
        if not mp.exists():
            raise EmbedderUnavailable(f"model file not found: {mp}")
        self._session = ort.InferenceSession(
            str(mp), providers=["CPUExecutionProvider"]
        )
        self._input_name = self._session.get_inputs()[0].name

    def embed(self, image_path: Path, faces: list[DetectedFace]) -> list[np.ndarray]:
        if not faces:
            return []
        try:
            import cv2

            img = cv2.imread(str(image_path))
            if img is None:
                raise EmbedderUnavailable(f"could not read image: {image_path}")
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        except Exception as exc:
            raise EmbedderUnavailable("OpenCV required to read/align faces") from exc

        out: list[np.ndarray] = []
        for face in faces:
            crop = self._face_crop(img, face)
            blob = crop.astype(np.float32) / 255.0
            blob = np.transpose(blob, (2, 0, 1))[None, ...]  # NCHW
            vec = self._session.run(None, {self._input_name: blob})[0][0]
            out.append(l2_normalize(np.asarray(vec, dtype=np.float32)))
        return out

    def _face_crop(self, img: np.ndarray, face: DetectedFace) -> np.ndarray:
        """5-point aligned crop when landmarks are present; else a bbox crop.

        Alignment is what SFace expects (it was trained on template-aligned
        faces); the bbox fallback keeps detectors without landmarks working.
        """
        pts = (face.landmarks or {}).get(LANDMARKS_POINTS5_KEY)
        if pts and len(pts) == 5:
            aligned = _align_5point(img, pts, self._input_size)
            if aligned is not None:
                return aligned
        return _crop_normalized(img, face.bbox, self._input_size)


class SFaceEmbedder(_OnnxFaceEmbedder):
    """SFace — Apache-2.0, 128-dim, commercial-safe. The default embedder."""

    name = "sface"
    dim = 128
    license_commercial = True


class ArcFaceEmbedder(_OnnxFaceEmbedder):
    """ArcFace / buffalo_l — 512-dim. FLAGGED NON-COMMERCIAL (private use only)."""

    name = "arcface"
    dim = 512
    license_commercial = False


def make_embedder(name: str = "sface", **cfg: object) -> FaceEmbedder:
    """Construct an embedder by name. Default ``sface`` (commercial-safe).

    ``cfg`` carries the resolved model paths (e.g. ``sface_model_path``).
    Raises ``EmbedderUnavailable`` if deps/model missing, ``ValueError`` for an
    unknown name.
    """
    if name == "sface":
        path = cfg.get("sface_model_path")
        if not path:
            raise EmbedderUnavailable("sface_model_path not configured")
        return SFaceEmbedder(str(path))
    if name == "arcface":
        path = cfg.get("arcface_model_path")
        if not path:
            raise EmbedderUnavailable("arcface_model_path not configured")
        return ArcFaceEmbedder(str(path))
    raise ValueError(f"unknown face embedder {name!r}; known: ['sface', 'arcface']")
