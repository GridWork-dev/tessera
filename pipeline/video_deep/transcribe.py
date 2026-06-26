"""Audio transcription — faster-whisper, lazily imported + guarded.

Choice (see the lane spec): **faster-whisper** (CTranslate2). One pip wheel runs
CPU on the Mac and CUDA on the rented box from the same code, returns segment
timestamps natively, and is ~4x faster than reference whisper at equal accuracy —
the right fit for a "build now, run on a rented GPU later" job that must also be
unit-testable locally. whisper.cpp (separate binary + GGUF) and MLX-whisper
(Mac-only, won't carry to CUDA) were rejected for this lane.

Audio is LOCAL — Whisper never touches the network. The dep is lazy-imported so
this module (and its pure-logic ``segments_for_scene`` test) imports on a box
without faster-whisper installed; ``transcribe_audio`` raises a clear install
hint if called without it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MODEL_SIZE = "base"


@dataclass(frozen=True)
class TranscriptSegment:
    """One transcript cue: absolute ``[start, end]`` seconds in the source video."""

    start: float
    end: float
    text: str
    language: str | None = None


def transcribe_audio(
    video_path: Path | str,
    *,
    model_size: str = DEFAULT_MODEL_SIZE,
    device: str = "auto",
    compute_type: str = "default",
    language: str | None = None,
) -> list[TranscriptSegment]:
    """Transcribe a video's audio track -> ordered ``TranscriptSegment`` list.

    Lazy-imports ``faster_whisper``; raises ``RuntimeError`` with an install hint
    if absent. ``device='auto'`` lets CTranslate2 pick CPU/CUDA — the SAME call
    works on the Mac and the rented GPU. ``language=None`` auto-detects. Returns
    ``[]`` for a silent/audio-less clip.
    """
    try:
        from faster_whisper import WhisperModel  # lazy heavy import
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise RuntimeError(
            "faster-whisper not installed; `pip install faster-whisper` to "
            "transcribe scene audio"
        ) from exc

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, info = model.transcribe(str(video_path), language=language)
    detected = getattr(info, "language", None) or language
    out: list[TranscriptSegment] = []
    for seg in segments:  # generator — materialize once
        text = (getattr(seg, "text", "") or "").strip()
        if not text:
            continue
        out.append(
            TranscriptSegment(
                start=float(getattr(seg, "start", 0.0) or 0.0),
                end=float(getattr(seg, "end", 0.0) or 0.0),
                text=text,
                language=detected,
            )
        )
    return out


def segments_for_scene(
    segments: list[TranscriptSegment], start: float, end: float
) -> list[TranscriptSegment]:
    """Clip whole-video segments to a scene's ``[start, end]`` window (pure).

    A segment is kept if it OVERLAPS the window (its midpoint is the tie-breaker
    for cues that straddle a cut). Pure + dep-free so it unit-tests without
    Whisper. Order is preserved.
    """
    kept: list[TranscriptSegment] = []
    for seg in segments:
        # Overlap test, then assign by midpoint so a straddling cue lands in one
        # scene only (no double-counting across the boundary).
        if seg.end <= start or seg.start >= end:
            continue
        midpoint = (seg.start + seg.end) / 2.0
        if start <= midpoint < end:
            kept.append(seg)
    return kept


def persist_scene_transcript(
    conn,
    scene_id: int,
    segments: list[TranscriptSegment],
    *,
    model: str,
    run_id: int | None = None,
) -> int:
    """Write ``scene_transcripts`` rows for a scene; return rows written.

    Idempotent: deletes any existing segments for ``scene_id`` first (re-run
    safe), then inserts the ordered window. ``conn`` is a raw sqlite3 connection
    (the single-writer path). Caller commits.
    """
    conn.execute("DELETE FROM scene_transcripts WHERE scene_id = ?", (int(scene_id),))
    now = datetime.now().isoformat()
    written = 0
    for index, seg in enumerate(segments):
        conn.execute(
            "INSERT INTO scene_transcripts "
            "(scene_id, segment_index, start_time, end_time, text, language, "
            "model, run_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                int(scene_id),
                index,
                float(seg.start),
                float(seg.end),
                seg.text,
                seg.language,
                model,
                run_id,
                now,
            ),
        )
        written += 1
    return written
