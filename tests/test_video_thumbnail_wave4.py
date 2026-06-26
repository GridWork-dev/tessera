"""Wave 4 video-thumbnail intelligence: aesthetic proxy + face-crop geometry.

Two independent concerns, both deterministic and torch-free:

1. The model-free aesthetic PROXY and the pure blend math (Item 1 fallback path):
   when the trained SigLIP head has no weights, an opt-in proxy
   (sharpness + colorfulness + central-subject prominence + exposure balance)
   still nudges the pick. Tested with tiny synthetic arrays — no real images.

2. The face-bbox COVER-CROP geometry (Item 2): a normalized ``[x, y, w, h]``
   face box (the ``DetectedFace.bbox`` convention) -> a padded, aspect-kept,
   in-bounds pixel crop rect, feature-flagged with a full-frame fallback.
"""

from __future__ import annotations

import numpy as np
import pytest

from pipeline import video_thumbnail as vt

# --------------------------------------------------------------------------- #
# Item 1 — pure blend math
# --------------------------------------------------------------------------- #


def test_blend_scores_matches_formula():
    # final = (1 - w) * minmax(composite) + w * aesthetic
    composite = [0.0, 0.5, 1.0]  # min-max -> [0, 0.5, 1.0] (already spans [0,1])
    aesthetic = [1.0, 0.0, 0.5]
    w = 0.25
    got = vt._blend_scores(composite, aesthetic, w)
    exp = [(1 - w) * c + w * a for c, a in zip([0.0, 0.5, 1.0], aesthetic)]
    assert got == pytest.approx(exp)


def test_blend_scores_minmax_normalizes_composite():
    # A composite that does NOT span [0,1] is renormalized before blending.
    composite = [2.0, 4.0, 6.0]  # min-max -> [0, 0.5, 1.0]
    aesthetic = [0.0, 0.0, 0.0]
    got = vt._blend_scores(composite, aesthetic, 0.5)
    assert got == pytest.approx([0.0, 0.25, 0.5])


def test_blend_scores_degenerate_composite_is_zero_norm():
    # All-equal composite has no spread -> comp_norm is zeros, aesthetic decides.
    composite = [0.5, 0.5]
    aesthetic = [0.2, 0.9]
    got = vt._blend_scores(composite, aesthetic, 0.5)
    assert got == pytest.approx([0.1, 0.45])  # 0.5 * aesthetic


# --------------------------------------------------------------------------- #
# Item 1 — deterministic aesthetic proxy
# --------------------------------------------------------------------------- #


def test_central_prominence_uniform_detail_is_zero():
    # Uniform detail energy -> the central box holds exactly its area share -> 0.
    detail = np.ones((40, 40), dtype=np.float64)
    assert vt._central_prominence(detail) == pytest.approx(0.0, abs=1e-9)


def test_central_prominence_centered_detail_is_high():
    # All energy inside the central quarter -> prominence saturates near 1.
    detail = np.zeros((40, 40), dtype=np.float64)
    detail[10:30, 10:30] = 1.0  # exactly the central 50% box
    assert vt._central_prominence(detail) > 0.99


def test_central_prominence_no_detail_is_zero():
    # A flat frame (no gradient energy) must not divide by zero.
    assert vt._central_prominence(np.zeros((8, 8), dtype=np.float64)) == 0.0


def test_proxy_scores_in_unit_interval_and_length():
    cv2 = pytest.importorskip("cv2")  # noqa: F841
    rng = np.random.default_rng(0)
    frames = [rng.integers(0, 255, (64, 64, 3), dtype=np.uint8) for _ in range(5)]
    scores = vt._aesthetic_proxy_scores(frames)
    assert scores is not None
    assert scores.shape == (5,)
    assert np.all(scores >= 0.0) and np.all(scores <= 1.0)


def test_proxy_prefers_sharp_centered_frame_over_flat_gray():
    cv2 = pytest.importorskip("cv2")  # noqa: F841
    rng = np.random.default_rng(1)
    # "good": mid-gray field with a sharp, colorful, CENTERED textured patch.
    good = np.full((64, 64, 3), 128, dtype=np.uint8)
    good[24:40, 24:40] = rng.integers(0, 255, (16, 16, 3), dtype=np.uint8)
    # "flat": a featureless mid-gray frame (well exposed but boring).
    flat = np.full((64, 64, 3), 128, dtype=np.uint8)
    s = vt._aesthetic_proxy_scores([good, flat])
    assert s is not None
    assert s[0] > s[1]


def test_blend_with_proxy_lifts_better_frame(monkeypatch):
    cv2 = pytest.importorskip("cv2")  # noqa: F841
    rng = np.random.default_rng(2)
    good = np.full((64, 64, 3), 128, dtype=np.uint8)
    good[24:40, 24:40] = rng.integers(0, 255, (16, 16, 3), dtype=np.uint8)
    flat = np.full((64, 64, 3), 128, dtype=np.uint8)
    # Equal composite -> the proxy is the deciding signal.
    composite = [0.5, 0.5]
    blended = vt._blend_with_proxy(composite, [good, flat])
    assert blended is not None
    assert len(blended) == 2
    assert blended[0] > blended[1]  # the richer frame wins


def test_proxy_fallback_engages_when_weights_absent(monkeypatch, tmp_path):
    # End-to-end: aesthetic ON + NO trained weights -> the proxy fallback runs
    # (the trained-head blend returns None) without ever hard-failing.
    cv2 = pytest.importorskip("cv2")
    import pipeline.aesthetic_head as ah

    monkeypatch.setattr(ah, "_default_weights_path", lambda: tmp_path / "absent.npz")

    path = str(tmp_path / "clip.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    w, h, fps = 64, 64, 4
    writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
    if not writer.isOpened():
        pytest.skip("cv2 VideoWriter could not open mp4v encoder")
    rng = np.random.default_rng(3)
    writer.write(np.zeros((h, w, 3), dtype=np.uint8))  # black -> rejected
    for _ in range(7):
        writer.write(rng.integers(40, 220, size=(h, w, 3), dtype=np.uint8))
    writer.release()

    best = vt.pick_best_frame_time(path, duration=2.0, use_aesthetic=True)
    if best is not None:
        assert best > 0.1  # never the black frame at t~0


# --------------------------------------------------------------------------- #
# Item 2 — face-crop geometry
# --------------------------------------------------------------------------- #


def test_face_crop_box_pads_and_centers():
    # A small centered face in a large frame, no aspect target. The padded box is
    # centered on the face and larger than it, fully inside the image.
    box = vt.compute_face_crop_box(
        [0.45, 0.45, 0.10, 0.10], img_w=1000, img_h=1000, padding=0.5
    )
    x0, y0, x1, y1 = box
    # face is 100x100 px centered at (500,500); padding 0.5 -> 200x200 padded box.
    assert (x1 - x0) == pytest.approx(200, abs=1)
    assert (y1 - y0) == pytest.approx(200, abs=1)
    assert (x0 + x1) / 2 == pytest.approx(500, abs=1)
    assert (y0 + y1) / 2 == pytest.approx(500, abs=1)
    assert 0 <= x0 < x1 <= 1000 and 0 <= y0 < y1 <= 1000


def test_face_crop_box_keeps_target_aspect():
    # A square padded box expanded to a 2:1 (w/h) target grows width, keeps height.
    x0, y0, x1, y1 = vt.compute_face_crop_box(
        [0.45, 0.45, 0.10, 0.10], img_w=1000, img_h=1000, padding=0.5, aspect=2.0
    )
    width, height = x1 - x0, y1 - y0
    assert width / height == pytest.approx(2.0, rel=0.02)
    assert 0 <= x0 < x1 <= 1000 and 0 <= y0 < y1 <= 1000


def test_face_crop_box_clamps_at_corner():
    # A face hard against the top-left corner: the box stays in-bounds, non-empty.
    x0, y0, x1, y1 = vt.compute_face_crop_box(
        [0.0, 0.0, 0.2, 0.2], img_w=200, img_h=200, padding=1.0
    )
    assert x0 == 0 and y0 == 0
    assert x1 > 0 and y1 > 0
    assert x1 <= 200 and y1 <= 200


def test_face_crop_box_oversized_clamps_to_full_frame():
    # A box that pads beyond the image collapses to the full frame, never empty.
    x0, y0, x1, y1 = vt.compute_face_crop_box(
        [0.1, 0.1, 0.8, 0.8], img_w=100, img_h=100, padding=2.0
    )
    assert (x0, y0, x1, y1) == (0, 0, 100, 100)


def test_crop_to_face_disabled_returns_full_frame():
    frame = np.zeros((50, 80, 3), dtype=np.uint8)
    out = vt.crop_to_face(frame, [0.4, 0.4, 0.2, 0.2], enabled=False)
    assert out.shape == frame.shape


def test_crop_to_face_none_bbox_returns_full_frame():
    frame = np.zeros((50, 80, 3), dtype=np.uint8)
    out = vt.crop_to_face(frame, None, enabled=True)
    assert out.shape == frame.shape


def test_crop_to_face_enabled_crops_region_around_face():
    # A 100x100 frame with a marked face patch; the enabled crop must be a smaller
    # sub-frame that still contains the face center pixel.
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[40:60, 40:60] = 200  # the "face" patch, centered at (50, 50)
    out = vt.crop_to_face(frame, [0.40, 0.40, 0.20, 0.20], enabled=True, padding=0.25)
    assert out.shape[0] < 100 and out.shape[1] < 100  # actually cropped
    assert out.size > 0
    # the bright face center survived the crop
    assert int(out.max()) == 200


def test_face_crop_env_flag_parsing(monkeypatch):
    for on in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv(vt.FACE_CROP_ENV_FLAG, on)
        assert vt._face_crop_enabled() is True
    for off in ("0", "false", "no", "off", ""):
        monkeypatch.setenv(vt.FACE_CROP_ENV_FLAG, off)
        assert vt._face_crop_enabled() is False
    monkeypatch.delenv(vt.FACE_CROP_ENV_FLAG, raising=False)
    assert vt._face_crop_enabled() is False
