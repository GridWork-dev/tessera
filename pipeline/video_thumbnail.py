"""Heuristic 'good frame' selection for video posters (Wave 2a + Wave 4 head).

Pick a representative, attractive frame instead of a fixed 10s grab. Pure CPU
OpenCV scoring over candidate frames; sub-second per video. Returns a timestamp
(seconds) or None — None means 'caller, keep the existing fixed-seek poster'
(graceful degrade when cv2 is unavailable or the video can't be read).

Wave 4 upgrades (opt-in, default OFF):

* **Aesthetic frame pick.** A LAION-style linear aesthetic head over the
  already-computed SigLIP 1152-dim image embeddings (see
  ``pipeline/aesthetic_head.py``) re-ranks the surviving candidate frames. When
  trained weights are present AND SigLIP loads, frames are embedded and the head
  score is *blended* with the OpenCV composite for "actually attractive" picks.
  When weights are absent, a deterministic, model-free **aesthetic proxy**
  (sharpness + colorfulness + central-subject prominence + exposure balance) is
  blended instead, so the flag is useful before any head has been trained. Every
  step degrades silently: a missing weights file, no torch/transformers, or any
  embed error just falls back to the next signal — the poster pipeline NEVER
  hard-fails on this path.

* **Face-cropped covers.** ``crop_to_face`` tightens a chosen cover frame to a
  detected face bounding box (the normalized ``[x, y, w, h]`` top-left
  ``DetectedFace`` convention from ``pipeline/faces/detector.py``) with padding
  and a kept aspect ratio. Feature-flagged and fully reversible: no face, no
  bbox, or the flag off -> the full frame is returned unchanged.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence

import numpy as np

logger = logging.getLogger(__name__)

try:  # cv2 is in the venv but optional; degrade if absent.
    import cv2  # type: ignore
except Exception:  # noqa: BLE001
    cv2 = None  # type: ignore


# --- Wave 4 aesthetic-head config (self-contained; no settings.py change) ------
#
# Default OFF. Enable per-box with the env var (consistent with the project's
# MEDIA_PIPELINE_* convention) or per-call via ``pick_best_frame_time(...,
# use_aesthetic=True)``. Even when enabled, the head only engages if trained
# weights (``models/aesthetic_siglip.npz``) AND SigLIP are both available;
# otherwise behavior is identical to the composite-only path.
AESTHETIC_ENV_FLAG = "MEDIA_PIPELINE_VIDEO_AESTHETIC"
# Blend weight: final = (1 - w) * composite_norm + w * aesthetic. The composite
# stays the safety net (the head is a tie-breaker / nudge, never the sole vote).
# The same weight blends either signal: the trained SigLIP head when weights are
# present, else the deterministic proxy fallback below.
AESTHETIC_BLEND_WEIGHT = 0.5

# --- Wave 4 face-crop config (Item 2; self-contained) --------------------------
#
# Default OFF. When ON and a face bbox is available for the chosen cover frame,
# ``crop_to_face`` tightens the poster to the face region (padded, aspect kept).
# Independent of the aesthetic flag: frame *selection* vs cover *framing*.
FACE_CROP_ENV_FLAG = "MEDIA_PIPELINE_VIDEO_FACE_CROP"
# Padding added around the face box as a fraction of its size, per side (0.6 ->
# the crop is 1 + 2*0.6 = 2.2x the face box in each axis before aspect/clamp).
FACE_CROP_PADDING = 0.6


def _flag_on(name: str) -> bool:
    """True if env var ``name`` is set to a truthy token (default OFF)."""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _aesthetic_enabled() -> bool:
    """True if the env flag opts the aesthetic head/proxy in (default OFF)."""
    return _flag_on(AESTHETIC_ENV_FLAG)


def _face_crop_enabled() -> bool:
    """True if the env flag opts face-cropped covers in (default OFF)."""
    return _flag_on(FACE_CROP_ENV_FLAG)


def _candidate_times(
    duration: float, scenes: list[tuple[float, float]] | None, n: int = 12
) -> list[float]:
    if scenes:
        mids = [(s + e) / 2.0 for s, e in scenes]
        # drop the first/last scene midpoints (intros / end-cards) when we have enough
        return mids[1:-1] if len(mids) >= 4 else mids
    if duration <= 0:
        return [0.0]
    lo, hi = 0.08 * duration, 0.92 * duration
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


def _colorfulness(bgr: np.ndarray) -> float:
    """Hasler–Süsstrunk M3 colorfulness."""
    b, g, r = (
        bgr[..., 0].astype("float"),
        bgr[..., 1].astype("float"),
        bgr[..., 2].astype("float"),
    )
    rg = r - g
    yb = 0.5 * (r + g) - b
    std = float(np.sqrt(rg.std() ** 2 + yb.std() ** 2))
    mean = float(np.sqrt(rg.mean() ** 2 + yb.mean() ** 2))
    return std + 0.3 * mean


def _score_frame(bgr: np.ndarray) -> float | None:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    mean = float(gray.mean())
    if mean < 12 or mean > 245:  # near-black or blown-out
        return None
    var = float(gray.var())
    if var < 25:  # near-uniform (title card / blank)
        return None
    sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    exposure = 1.0 - abs(mean - 128.0) / 128.0  # 1 at mid-gray, 0 at extremes
    color = _colorfulness(bgr)
    # normalize loosely; ranking is what matters, not absolute scale
    return (
        0.5 * min(sharp / 1000.0, 1.0) + 0.3 * exposure + 0.2 * min(color / 80.0, 1.0)
    )


def _embed_frames_siglip(frames_bgr: list[np.ndarray]) -> np.ndarray | None:
    """Embed BGR frames with the SigLIP image tower -> ``(n, 1152)`` or None.

    Reuses ``pipeline.tier1_embedder.Tier1Embedder`` (same model + processor +
    pooler_output read as the rest of the pipeline) so the head sees vectors in
    the exact space it was trained on. Heavy deps (torch/transformers) are
    imported lazily inside the embedder; ANY failure (no torch, load error,
    bad frame) returns None so the caller falls back to the composite.
    """
    if not frames_bgr:
        return None
    try:
        import torch  # lazy: MacBook venv may lack torch
        from PIL import Image as PILImage

        from pipeline.tier1_embedder import Tier1Embedder

        embedder = Tier1Embedder()
        embedder._load()  # populates processor + model (mps/cpu)

        # cv2 frames are BGR; SigLIP expects RGB PIL images.
        imgs = [
            PILImage.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)) for f in frames_bgr
        ]
        inputs = embedder.processor(images=imgs, return_tensors="pt").to(
            embedder.device
        )
        with torch.no_grad():
            out = embedder.model.get_image_features(**inputs)
        mat = out.pooler_output.detach().cpu().numpy().astype(np.float32)
        return mat  # the head L2-normalizes internally
    except Exception as exc:  # noqa: BLE001 - never break poster pick on embed failure
        logger.debug("SigLIP frame embed unavailable (%s) — composite only", exc)
        return None


def _blend_scores(
    composite: Sequence[float], aesthetic: Sequence[float], w: float
) -> list[float]:
    """Pure blend math: ``final = (1 - w) * minmax(composite) + w * aesthetic``.

    Min-max normalizes ``composite`` into [0, 1] first so the OpenCV signal and
    the [0, 1] aesthetic signal sit on a comparable scale. An all-equal composite
    has no spread, so its normalized form is all-zeros and the aesthetic signal
    alone decides the ranking. Returns a plain list (same order/length).
    """
    comp = np.asarray(composite, dtype=np.float64)
    lo, hi = float(comp.min()), float(comp.max())
    comp_norm = (comp - lo) / (hi - lo) if hi > lo else np.zeros_like(comp)
    aes = np.asarray(aesthetic, dtype=np.float64)
    blended = (1.0 - w) * comp_norm + w * aes
    return [float(x) for x in blended]


def _blend_with_aesthetic(
    composite: list[float], frames_bgr: list[np.ndarray]
) -> list[float] | None:
    """Blend the composite with the *trained* SigLIP aesthetic head, or None.

    Returns a new score list (same order/length as ``composite``) when trained
    weights are present AND the frames embed cleanly; otherwise None so the
    caller falls back (to the proxy, then the composite). The head never
    fabricates a score from nothing — a missing weights file means None here.
    """
    from pipeline.aesthetic_head import load_aesthetic_head

    head = load_aesthetic_head()
    if head is None:
        return None  # no trained weights -> defer to the proxy / composite

    embeddings = _embed_frames_siglip(frames_bgr)
    if embeddings is None or len(embeddings) != len(composite):
        return None

    aesthetic = head.score(embeddings)
    return _blend_scores(composite, aesthetic, AESTHETIC_BLEND_WEIGHT)


def _central_prominence(detail: np.ndarray) -> float:
    """Share of detail energy in the central 50% box, rescaled to [0, 1].

    ``detail`` is a per-pixel energy map (e.g. ``|Laplacian|``). A uniform map
    puts exactly the central box's *area* share of energy there -> 0.0; energy
    fully concentrated in the centre -> 1.0. This proxies "is there a prominent,
    well-placed subject" without any model. Returns 0.0 for a flat (no-energy)
    frame rather than dividing by zero.
    """
    total = float(detail.sum())
    if total <= 0.0:
        return 0.0
    h, w = detail.shape[:2]
    r0, r1 = h // 4, h - h // 4
    c0, c1 = w // 4, w - w // 4
    central = float(detail[r0:r1, c0:c1].sum())
    frac = central / total
    area_frac = ((r1 - r0) * (c1 - c0)) / float(h * w)
    if area_frac >= 1.0:  # degenerate tiny frame -> no meaningful "centre"
        return 0.0
    return float(np.clip((frac - area_frac) / (1.0 - area_frac), 0.0, 1.0))


def _proxy_one(bgr: np.ndarray) -> float:
    """Deterministic, model-free aesthetic proxy for one BGR frame in [0, 1].

    A documented linear mix of four bounded cues, each soft-capped into [0, 1]:
    sharpness (Laplacian variance), colorfulness (Hasler-Süsstrunk), central
    subject prominence, and exposure balance. Stand-in for a trained head before
    weights exist; the weights mirror the OpenCV composite's emphasis on detail.
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    sharp = min(float(lap.var()) / 1000.0, 1.0)
    mean = float(gray.mean())
    exposure = 1.0 - abs(mean - 128.0) / 128.0  # 1 at mid-gray, 0 at extremes
    color = min(_colorfulness(bgr) / 80.0, 1.0)
    prominence = _central_prominence(np.abs(lap))
    return 0.35 * sharp + 0.20 * color + 0.25 * prominence + 0.20 * exposure


def _aesthetic_proxy_scores(frames_bgr: list[np.ndarray]) -> np.ndarray | None:
    """Per-frame proxy scores in [0, 1], or None when cv2 is unavailable.

    The model-free fallback for ``_blend_with_aesthetic``: it needs no weights,
    no torch, and runs in microseconds over the handful of candidate frames.
    """
    if cv2 is None or not frames_bgr:
        return None
    return np.asarray([_proxy_one(f) for f in frames_bgr], dtype=np.float64)


def _blend_with_proxy(
    composite: list[float], frames_bgr: list[np.ndarray]
) -> list[float] | None:
    """Blend the composite with the deterministic proxy, or None to skip.

    The fallback path when no trained head weights are present: same blend math
    and weight as the head, so behavior is consistent whichever signal is live.
    """
    proxy = _aesthetic_proxy_scores(frames_bgr)
    if proxy is None or len(proxy) != len(composite):
        return None
    return _blend_scores(composite, proxy, AESTHETIC_BLEND_WEIGHT)


def pick_best_frame_time(
    video_path: str,
    duration: float,
    scenes: list[tuple[float, float]] | None = None,
    *,
    use_aesthetic: bool | None = None,
) -> float | None:
    """Return the timestamp (s) of the best candidate frame, or None to degrade.

    ``use_aesthetic`` opts the Wave 4 aesthetic pass in/out: None (default)
    consults the ``MEDIA_PIPELINE_VIDEO_AESTHETIC`` env flag; True/False force it.
    When on, the pick is re-ranked by the trained SigLIP head (weights + SigLIP
    present), else by the deterministic proxy; if neither yields a blend the
    OpenCV composite alone decides, exactly as before.
    """
    if cv2 is None:
        return None
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None

    want_aesthetic = _aesthetic_enabled() if use_aesthetic is None else use_aesthetic

    try:
        # Collect every surviving candidate (time, composite score, frame) so the
        # optional aesthetic pass can re-score the same set in one batch.
        times: list[float] = []
        comp_scores: list[float] = []
        frames: list[np.ndarray] = []
        for t in _candidate_times(duration, scenes):
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            s = _score_frame(frame)
            if s is None:
                continue
            times.append(t)
            comp_scores.append(s)
            # Keep a copy only if we might run the aesthetic pass (memory-light:
            # candidate frames are few and small).
            frames.append(frame.copy() if want_aesthetic else frame)

        if not times:
            return None

        scores = comp_scores
        if want_aesthetic:
            # Prefer the trained SigLIP head; fall back to the deterministic
            # proxy when no weights exist; else the composite stands unchanged.
            blended = _blend_with_aesthetic(comp_scores, frames)
            if blended is None:
                blended = _blend_with_proxy(comp_scores, frames)
            if blended is not None:
                scores = blended

        best_idx = int(np.argmax(np.asarray(scores)))
        return times[best_idx]
    finally:
        cap.release()


# --------------------------------------------------------------------------- #
# Wave 4 Item 2 — face-bbox-cropped cover thumbnails.
#
# Pure geometry + a thin array crop, kept here (not in the ffmpeg poster path) so
# the math is unit-testable with synthetic arrays and the live ingest/repick code
# can adopt it as a drop-in hook: feed it the chosen cover frame plus a
# ``DetectedFace.bbox`` (normalized ``[x, y, w, h]``, top-left) and write the
# returned crop instead of the full frame. No bbox / flag off -> full frame.
# --------------------------------------------------------------------------- #
def compute_face_crop_box(
    bbox: Sequence[float],
    img_w: int,
    img_h: int,
    *,
    padding: float = FACE_CROP_PADDING,
    aspect: float | None = None,
) -> tuple[int, int, int, int]:
    """Pixel crop rect ``(x0, y0, x1, y1)`` around a normalized face ``bbox``.

    ``bbox`` is the ``DetectedFace`` convention: normalized ``[x, y, w, h]`` with
    a top-left origin. The face box is padded by ``padding`` * its size on each
    side, optionally grown (never shrunk) to a target ``aspect`` (width / height),
    then shifted to sit inside the image; a box larger than the image clamps to
    the full frame. Always returns a non-empty, in-bounds integer rect.
    """
    fx, fy, fw, fh = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    # Normalized -> pixel, centre + half-extents.
    cx = (fx + fw / 2.0) * img_w
    cy = (fy + fh / 2.0) * img_h
    bw = max(1.0, fw * img_w)
    bh = max(1.0, fh * img_h)

    # Pad symmetrically.
    new_w = bw * (1.0 + 2.0 * padding)
    new_h = bh * (1.0 + 2.0 * padding)

    # Grow the deficient axis to hit the target aspect (never crop tighter).
    if aspect is not None and aspect > 0.0:
        if new_w / new_h < aspect:
            new_w = new_h * aspect
        else:
            new_h = new_w / aspect

    # Box can't exceed the frame; if it does, it spans that whole axis.
    new_w = min(new_w, float(img_w))
    new_h = min(new_h, float(img_h))

    # Place centred, then shift inside the bounds (keeps aspect off-centre).
    x0 = cx - new_w / 2.0
    y0 = cy - new_h / 2.0
    x0 = min(max(0.0, x0), img_w - new_w)
    y0 = min(max(0.0, y0), img_h - new_h)

    ix0, iy0 = int(round(x0)), int(round(y0))
    ix1, iy1 = int(round(x0 + new_w)), int(round(y0 + new_h))
    # Guard against rounding collapsing the box.
    ix1 = min(img_w, max(ix0 + 1, ix1))
    iy1 = min(img_h, max(iy0 + 1, iy1))
    return ix0, iy0, ix1, iy1


def crop_to_face(
    frame_bgr: np.ndarray,
    bbox: Sequence[float] | None,
    *,
    enabled: bool | None = None,
    padding: float = FACE_CROP_PADDING,
    aspect: float | None = None,
) -> np.ndarray:
    """Crop ``frame_bgr`` to the face region, or return it unchanged (fallback).

    ``enabled`` opts the crop in/out: None (default) consults the
    ``MEDIA_PIPELINE_VIDEO_FACE_CROP`` env flag; True/False force it. With the
    feature off OR ``bbox`` None the FULL frame is returned (the reversible
    fallback). ``aspect`` defaults to the source frame's aspect ratio so the
    cropped cover keeps the poster's shape.
    """
    use = _face_crop_enabled() if enabled is None else enabled
    if not use or bbox is None:
        return frame_bgr
    h, w = frame_bgr.shape[:2]
    if h == 0 or w == 0:
        return frame_bgr
    if aspect is None:
        aspect = w / float(h)
    x0, y0, x1, y1 = compute_face_crop_box(bbox, w, h, padding=padding, aspect=aspect)
    return frame_bgr[y0:y1, x0:x1]
