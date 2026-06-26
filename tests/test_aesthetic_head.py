"""Tests for the LAION-style linear aesthetic head (Wave 4) and its wiring.

Three concerns, all deterministic and torch-free:

1. The linear head math (sigmoid(w . l2norm(x) + b)) with SYNTHETIC weights.
2. The absent / malformed weights -> None graceful fallback.
3. video_thumbnail's composite path still works (and is unchanged) when the
   aesthetic head is disabled — the default.
"""

from __future__ import annotations

import numpy as np
import pytest

from pipeline.aesthetic_head import (
    EMBEDDING_DIM,
    AestheticHead,
    _sigmoid,
    load_aesthetic_head,
)

# --- 1. linear head math, synthetic deterministic weights ---------------------


def _expected_score(w: np.ndarray, b: float, x: np.ndarray) -> float:
    xhat = x / np.linalg.norm(x)
    return float(1.0 / (1.0 + np.exp(-(float(xhat @ w) + b))))


def test_head_matches_hand_computed_sigmoid():
    rng = np.random.default_rng(0)
    w = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    b = 0.25
    x = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)

    head = AestheticHead(w, b)
    got = head.score(x)

    assert got.shape == (1,)
    assert got[0] == pytest.approx(_expected_score(w, b, x), abs=1e-5)


def test_head_scores_are_in_unit_interval():
    rng = np.random.default_rng(1)
    w = rng.standard_normal(EMBEDDING_DIM).astype(np.float32) * 10.0  # large logits
    head = AestheticHead(w, b=-3.0)
    batch = rng.standard_normal((16, EMBEDDING_DIM)).astype(np.float32)

    scores = head.score(batch)
    assert scores.shape == (16,)
    assert np.all(scores > 0.0) and np.all(scores < 1.0)


def test_head_is_l2_invariant_to_input_scale():
    # The head L2-normalizes internally, so scaling the raw embedding must not
    # change the score (callers may pass normalized or raw vectors).
    rng = np.random.default_rng(2)
    w = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    head = AestheticHead(w, b=0.0)
    x = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)

    s1 = head.score(x)
    s2 = head.score(x * 7.5)
    assert s1[0] == pytest.approx(s2[0], abs=1e-6)


def test_head_ranks_aligned_embedding_highest():
    # A frame whose embedding points along +w should outscore one along -w.
    w = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    w[0] = 5.0
    head = AestheticHead(w, b=0.0)

    aligned = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    aligned[0] = 1.0
    anti = -aligned

    s = head.score(np.stack([aligned, anti]))
    assert s[0] > 0.9  # sigmoid(5)
    assert s[1] < 0.1  # sigmoid(-5)


def test_head_rejects_wrong_weight_shape():
    with pytest.raises(ValueError):
        AestheticHead(np.zeros(10, dtype=np.float32), b=0.0)


def test_head_rejects_wrong_embedding_width():
    head = AestheticHead(np.zeros(EMBEDDING_DIM, dtype=np.float32), b=0.0)
    with pytest.raises(ValueError):
        head.score(np.zeros((1, 8), dtype=np.float32))


def test_sigmoid_is_numerically_stable_at_extremes():
    z = np.array([-1000.0, 0.0, 1000.0])
    out = _sigmoid(z)
    assert out[0] == pytest.approx(0.0, abs=1e-12)
    assert out[1] == pytest.approx(0.5, abs=1e-12)
    assert out[2] == pytest.approx(1.0, abs=1e-12)


# --- 2. weights loader: absent / malformed -> None ----------------------------


def test_load_returns_none_when_absent(tmp_path):
    missing = tmp_path / "nope.npz"
    assert load_aesthetic_head(missing) is None


def test_load_roundtrips_saved_weights(tmp_path):
    rng = np.random.default_rng(3)
    w = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    b = np.float32(-0.5)
    path = tmp_path / "aesthetic_siglip.npz"
    np.savez(path, w=w, b=b)

    head = load_aesthetic_head(path)
    assert head is not None
    np.testing.assert_allclose(head.w, w, rtol=0, atol=0)
    assert head.b == pytest.approx(float(b), abs=1e-6)

    # And it scores consistently with a directly-constructed head.
    x = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    assert head.score(x)[0] == pytest.approx(
        AestheticHead(w, float(b)).score(x)[0], abs=1e-6
    )


def test_load_returns_none_on_missing_arrays(tmp_path):
    # An .npz that exists but lacks 'w'/'b' must degrade to None, not raise.
    path = tmp_path / "aesthetic_siglip.npz"
    np.savez(path, not_w=np.zeros(EMBEDDING_DIM, dtype=np.float32))
    assert load_aesthetic_head(path) is None


def test_load_returns_none_on_corrupt_file(tmp_path):
    path = tmp_path / "aesthetic_siglip.npz"
    path.write_bytes(b"this is not a real npz archive")
    assert load_aesthetic_head(path) is None


def test_default_weights_path_absent_yields_none(monkeypatch, tmp_path):
    # With no weights file at the configured models dir, the no-arg loader is None
    # (the production default when the head hasn't been trained yet).
    import pipeline.aesthetic_head as ah

    monkeypatch.setattr(ah, "_default_weights_path", lambda: tmp_path / "absent.npz")
    assert ah.load_aesthetic_head() is None


# --- 3. video_thumbnail composite path unchanged when head disabled -----------


def test_pick_best_frame_degrades_without_video_default(tmp_path):
    # Default (env flag unset) -> composite-only, and an unreadable path degrades
    # to None exactly as before the Wave 4 wiring.
    from pipeline.video_thumbnail import pick_best_frame_time

    missing = tmp_path / "nope.mp4"
    assert pick_best_frame_time(str(missing), duration=10.0) is None


def test_aesthetic_disabled_by_default(monkeypatch):
    from pipeline import video_thumbnail as vt

    monkeypatch.delenv(vt.AESTHETIC_ENV_FLAG, raising=False)
    assert vt._aesthetic_enabled() is False


def test_aesthetic_env_flag_parsing(monkeypatch):
    from pipeline import video_thumbnail as vt

    for on in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv(vt.AESTHETIC_ENV_FLAG, on)
        assert vt._aesthetic_enabled() is True
    for off in ("0", "false", "no", "off", ""):
        monkeypatch.setenv(vt.AESTHETIC_ENV_FLAG, off)
        assert vt._aesthetic_enabled() is False


def test_blend_skips_when_weights_absent(monkeypatch, tmp_path):
    # With no weights, _blend_with_aesthetic returns None so the caller keeps the
    # composite — the head never fabricates a score from nothing.
    import pipeline.aesthetic_head as ah
    from pipeline import video_thumbnail as vt

    monkeypatch.setattr(ah, "_default_weights_path", lambda: tmp_path / "absent.npz")
    composite = [0.1, 0.9, 0.4]
    frames = [np.zeros((4, 4, 3), dtype=np.uint8) for _ in composite]
    assert vt._blend_with_aesthetic(composite, frames) is None


def test_blend_falls_back_when_siglip_unavailable(monkeypatch, tmp_path):
    # Weights present but SigLIP embed fails -> blend returns None (composite wins).
    import pipeline.aesthetic_head as ah
    from pipeline import video_thumbnail as vt

    w = np.ones(EMBEDDING_DIM, dtype=np.float32)
    path = tmp_path / "aesthetic_siglip.npz"
    np.savez(path, w=w, b=np.float32(0.0))
    monkeypatch.setattr(ah, "_default_weights_path", lambda: path)
    # Force the embed step to report "unavailable".
    monkeypatch.setattr(vt, "_embed_frames_siglip", lambda frames: None)

    composite = [0.2, 0.8]
    frames = [np.zeros((4, 4, 3), dtype=np.uint8) for _ in composite]
    assert vt._blend_with_aesthetic(composite, frames) is None


def test_blend_combines_scores_with_stub_embeddings(monkeypatch, tmp_path):
    # End-to-end blend with a deterministic stub embedder: a frame the head loves
    # (embedding == +w) should be lifted relative to one it dislikes (== -w),
    # while the composite still contributes its share.
    import pipeline.aesthetic_head as ah
    from pipeline import video_thumbnail as vt

    w = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    w[0] = 8.0
    path = tmp_path / "aesthetic_siglip.npz"
    np.savez(path, w=w, b=np.float32(0.0))
    monkeypatch.setattr(ah, "_default_weights_path", lambda: path)

    liked = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    liked[0] = 1.0
    disliked = -liked

    def fake_embed(frames):
        # First frame disliked (low aesthetic), second liked (high aesthetic).
        return np.stack([disliked, liked])

    monkeypatch.setattr(vt, "_embed_frames_siglip", fake_embed)

    # Equal composite scores -> the aesthetic head is the deciding signal.
    composite = [0.5, 0.5]
    frames = [np.zeros((4, 4, 3), dtype=np.uint8) for _ in composite]
    blended = vt._blend_with_aesthetic(composite, frames)
    assert blended is not None
    assert len(blended) == 2
    assert blended[1] > blended[0]  # the liked frame wins after blending


def test_pick_best_frame_aesthetic_off_matches_composite(tmp_path):
    # Synthesize a tiny clip; with the head OFF (default) the pick must come from
    # the composite path. Mirrors the existing video_thumbnail black-frame test.
    cv2 = pytest.importorskip("cv2")
    from pipeline.video_thumbnail import pick_best_frame_time

    path = str(tmp_path / "clip.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    w, h, fps = 64, 64, 4
    writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
    if not writer.isOpened():
        pytest.skip("cv2 VideoWriter could not open mp4v encoder")
    rng = np.random.default_rng(0)
    writer.write(np.zeros((h, w, 3), dtype=np.uint8))  # black -> rejected
    for _ in range(7):
        writer.write(rng.integers(40, 220, size=(h, w, 3), dtype=np.uint8))
    writer.release()

    best = pick_best_frame_time(path, duration=2.0, use_aesthetic=False)
    if best is not None:
        assert best > 0.1  # never the black frame at t~0
