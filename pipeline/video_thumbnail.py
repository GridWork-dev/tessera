"""Heuristic 'good frame' selection for video posters (Wave 2a + Wave 4 head).

Pick a representative, attractive frame instead of a fixed 10s grab. Pure CPU
OpenCV scoring over candidate frames; sub-second per video. Returns a timestamp
(seconds) or None — None means 'caller, keep the existing fixed-seek poster'
(graceful degrade when cv2 is unavailable or the video can't be read).

Wave 4 upgrade (opt-in, default OFF): a LAION-style linear aesthetic head over
the already-computed SigLIP 1152-dim image embeddings (see
``pipeline/aesthetic_head.py``). When enabled AND trained weights are present
AND SigLIP can be loaded, the surviving candidate frames are embedded and their
aesthetic score is *blended* with the OpenCV composite for "actually attractive"
picks. Every part of that path degrades silently: a missing weights file, no
torch/transformers, or any embed error falls straight back to the composite —
the poster pipeline NEVER hard-fails on the aesthetic head.
"""

from __future__ import annotations

import logging
import os

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
AESTHETIC_BLEND_WEIGHT = 0.5


def _aesthetic_enabled() -> bool:
    """True if the env flag opts the aesthetic head in (default OFF)."""
    return os.environ.get(AESTHETIC_ENV_FLAG, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


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


def _blend_with_aesthetic(
    composite: list[float], frames_bgr: list[np.ndarray]
) -> list[float] | None:
    """Blend the composite scores with aesthetic-head scores, or None to skip.

    Returns a new score list (same order/length as ``composite``) when the head
    is loadable and frames embed cleanly; otherwise None so the caller keeps the
    composite. Min-max normalizes the composite into [0, 1] before blending so
    the two signals are on a comparable scale (the head already emits (0, 1)).
    """
    from pipeline.aesthetic_head import load_aesthetic_head

    head = load_aesthetic_head()
    if head is None:
        return None  # no trained weights -> feature off, composite unchanged

    embeddings = _embed_frames_siglip(frames_bgr)
    if embeddings is None or len(embeddings) != len(composite):
        return None

    aesthetic = head.score(embeddings)

    comp = np.asarray(composite, dtype=np.float64)
    lo, hi = float(comp.min()), float(comp.max())
    comp_norm = (comp - lo) / (hi - lo) if hi > lo else np.zeros_like(comp)

    w = AESTHETIC_BLEND_WEIGHT
    blended = (1.0 - w) * comp_norm + w * aesthetic.astype(np.float64)
    return [float(x) for x in blended]


def pick_best_frame_time(
    video_path: str,
    duration: float,
    scenes: list[tuple[float, float]] | None = None,
    *,
    use_aesthetic: bool | None = None,
) -> float | None:
    """Return the timestamp (s) of the best candidate frame, or None to degrade.

    ``use_aesthetic`` opts the Wave 4 SigLIP aesthetic head in/out: None (default)
    consults the ``MEDIA_PIPELINE_VIDEO_AESTHETIC`` env flag; True/False force it.
    Even when on, the head only changes the pick if trained weights AND SigLIP are
    available — otherwise the OpenCV composite alone decides, exactly as before.
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
            blended = _blend_with_aesthetic(comp_scores, frames)
            if blended is not None:
                scores = blended

        best_idx = int(np.argmax(np.asarray(scores)))
        return times[best_idx]
    finally:
        cap.release()
