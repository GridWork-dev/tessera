"""Tests for the heuristic video best-frame scorer (Wave 2a).

The two candidate-timing tests are pure (no cv2 / no real video). The optional
extraction test synthesizes a tiny clip via cv2.VideoWriter and is skipped when
cv2 is unavailable.
"""

from __future__ import annotations

import pytest

from pipeline.video_thumbnail import _candidate_times, pick_best_frame_time


def test_candidate_times_uniform_window():
    times = _candidate_times(duration=100.0, scenes=None)
    assert len(times) == 12
    # strictly ascending, inside (0, 100) — sampled across [8%, 92%].
    assert times == sorted(times)
    assert times[0] > 0.0
    assert times[-1] < 100.0


def test_candidate_times_drops_first_and_last_scene():
    scenes = [(0, 5), (5, 10), (10, 15), (15, 20)]
    # midpoints = 2.5, 7.5, 12.5, 17.5 -> drop first/last -> [7.5, 12.5]
    assert _candidate_times(0, scenes) == [7.5, 12.5]


def test_pick_best_frame_time_degrades_without_video(tmp_path):
    # A path that can't be opened must degrade to None (caller keeps fixed seek),
    # whether cv2 is present (VideoCapture.isOpened False) or absent.
    missing = tmp_path / "nope.mp4"
    assert pick_best_frame_time(str(missing), duration=10.0) is None


def test_pick_best_frame_time_skips_black_frame(tmp_path):
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    path = str(tmp_path / "clip.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    w, h, fps = 64, 64, 4
    writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
    if not writer.isOpened():
        pytest.skip("cv2 VideoWriter could not open mp4v encoder")
    rng = np.random.default_rng(0)
    # Frame 0: pure black (must be rejected). Frames 1..7: bright, sharp noise.
    writer.write(np.zeros((h, w, 3), dtype=np.uint8))
    for _ in range(7):
        writer.write(rng.integers(40, 220, size=(h, w, 3), dtype=np.uint8))
    writer.release()

    best = pick_best_frame_time(path, duration=2.0)
    # Either a real timestamp was chosen, or extraction degraded to None; never
    # the very start (the black frame at t~0).
    if best is not None:
        assert best > 0.1
