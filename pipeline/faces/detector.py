"""Face detection — pluggable interface + Apple Vision on-device default.

Detection runs on-box. The default backend wraps **macOS Vision**
(``VNDetectFaceLandmarksRequest`` — detects faces AND their 2D landmarks in one
pass) via **pyobjc** — ANE-accelerated, free, and private. It is constructed
lazily; if pyobjc / Vision is not importable (non-mac or pyobjc missing)
construction raises ``DetectorUnavailable`` so callers can skip gracefully. A
future ONNX detector (YuNet) slots into ``make_detector`` without changing this
API.

Bounding boxes are returned NORMALIZED ``[x, y, w, h]`` in ``0..1`` with a
TOP-LEFT origin (PIL/SFace convention). Vision's native origin is bottom-left,
so we flip ``y`` on the way out. Each face also carries ``landmarks["points5"]``
— the 5 alignment points (normalized, top-left) the embedder warps to the SFace
template — when Vision returns landmarks for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class DetectorUnavailable(RuntimeError):
    """Raised when a detector's runtime dependency is not importable."""


@dataclass(frozen=True)
class DetectedFace:
    """One detected face. ``bbox`` is normalized ``[x, y, w, h]`` top-left."""

    bbox: list[float]
    confidence: float
    landmarks: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class FaceDetector(Protocol):
    """Detect faces in one image. Implementations run on-box only."""

    name: str

    def detect(self, image_path: Path) -> list[DetectedFace]: ...


def _vision_available() -> bool:
    """True if macOS Vision is importable via pyobjc."""
    try:
        import Quartz  # noqa: F401
        import Vision  # noqa: F401
    except Exception:
        return False
    return True


def _region_points(region: Any, w: int, h: int) -> list[tuple[float, float]]:
    """Pixel points (TOP-LEFT origin) for one VNFaceLandmarkRegion2D, or []."""
    import Foundation

    if region is None:
        return []
    try:
        pts = region.pointsInImageOfSize_(Foundation.NSMakeSize(w, h))  # BL origin px
        n = region.pointCount()
        # Vision's y is bottom-left; flip to top-left (PIL/cv2 convention).
        return [(float(pts[i].x), float(h) - float(pts[i].y)) for i in range(n)]
    except Exception:
        return []


def _points5_from_landmarks(lm: Any, w: int, h: int) -> list[list[float]] | None:
    """Derive the 5 alignment points (normalized, top-left) from Vision landmarks.

    Order matches the ArcFace template: [left_eye, right_eye, nose, left_mouth,
    right_mouth]. Left/right are assigned by image-x position (NOT Vision's
    subject-relative region names) so the correspondence is always consistent.
    Returns ``None`` if any required region is missing — caller falls back to a
    bbox crop.
    """
    if lm is None:
        return None
    eye_a = _region_points(getattr(lm, "leftEye", lambda: None)(), w, h)
    eye_b = _region_points(getattr(lm, "rightEye", lambda: None)(), w, h)
    nose = _region_points(getattr(lm, "nose", lambda: None)(), w, h)
    lips = _region_points(getattr(lm, "outerLips", lambda: None)(), w, h)
    if not (eye_a and eye_b and nose and lips):
        return None

    def _mean(pts: list[tuple[float, float]]) -> tuple[float, float]:
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    ca, cb = _mean(eye_a), _mean(eye_b)
    left_eye, right_eye = (ca, cb) if ca[0] <= cb[0] else (cb, ca)
    nose_c = _mean(nose)
    left_mouth = min(lips, key=lambda p: p[0])  # image-leftmost lip point
    right_mouth = max(lips, key=lambda p: p[0])  # image-rightmost lip point
    pts5 = [left_eye, right_eye, nose_c, left_mouth, right_mouth]
    return [[x / w, y / h] for (x, y) in pts5]


class VisionFaceDetector:
    """macOS Vision face detector (pyobjc). On-device, ANE-accelerated, free."""

    name = "apple_vision"

    def __init__(self) -> None:
        if not _vision_available():
            raise DetectorUnavailable(
                "macOS Vision / pyobjc not importable — install pyobjc-framework-Vision "
                "and pyobjc-framework-Quartz on macOS, or select a different detector."
            )

    def detect(self, image_path: Path) -> list[DetectedFace]:
        import Quartz
        import Vision

        url = Quartz.CFURLCreateWithFileSystemPath(
            None, str(image_path), Quartz.kCFURLPOSIXPathStyle, False
        )
        src = Quartz.CGImageSourceCreateWithURL(url, None)
        if src is None:
            raise DetectorUnavailable(f"could not open image: {image_path}")
        cg_image = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
        if cg_image is None:
            raise DetectorUnavailable(f"could not decode image: {image_path}")
        img_w = int(Quartz.CGImageGetWidth(cg_image))
        img_h = int(Quartz.CGImageGetHeight(cg_image))

        # Landmarks request: detects faces AND their 2D landmarks in one pass, so
        # the embedder can align to the canonical template (raw bbox crops collapse
        # identities). Falls back gracefully — faces without landmarks still embed.
        request = Vision.VNDetectFaceLandmarksRequest.alloc().init()
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
            cg_image, None
        )
        ok = handler.performRequests_error_([request], None)
        if not ok:
            return []

        faces: list[DetectedFace] = []
        for obs in request.results() or []:
            bb = obs.boundingBox()  # normalized, bottom-left origin
            x = float(bb.origin.x)
            w = float(bb.size.width)
            h = float(bb.size.height)
            # Vision origin is bottom-left; convert y to top-left.
            y = 1.0 - float(bb.origin.y) - h
            conf = float(getattr(obs, "confidence", lambda: 1.0)())
            landmarks: dict[str, Any] = {}
            pts5 = _points5_from_landmarks(obs.landmarks(), img_w, img_h)
            if pts5 is not None:
                landmarks["points5"] = pts5
            faces.append(
                DetectedFace(bbox=[x, y, w, h], confidence=conf, landmarks=landmarks)
            )
        return faces


def make_detector(name: str = "apple_vision") -> FaceDetector:
    """Construct a detector by name. ``apple_vision`` is the default.

    Raises ``DetectorUnavailable`` if the chosen backend's deps are missing,
    ``ValueError`` for an unknown name.
    """
    if name == "apple_vision":
        return VisionFaceDetector()
    raise ValueError(f"unknown face detector {name!r}; known: ['apple_vision']")
