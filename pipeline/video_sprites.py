"""
Scrub sprite sheet + WebVTT generation for the video player timeline.

A sprite sheet is a single image tiling one frame sampled every ``interval``
seconds (``fps=1/interval``); the WebVTT file maps each timeline window to the
matching tile's ``#xywh`` region so the player can show a thumbnail on hover.

THE #1 BUG GUARDED HERE: the WebVTT cue interval MUST EQUAL the sprite sampling
interval. The sheet samples one frame every ``interval`` seconds, so cue ``i``
MUST cover ``[i*interval, (i+1)*interval)`` — any other cue spacing desyncs the
thumbnails from the timeline. ``write_webvtt`` derives cue times straight from
the same ``interval`` to make this impossible to get wrong.

ffmpeg is invoked through a thin ``subprocess`` wrapper so tests hit the real
binary on a tiny clip.
"""

from __future__ import annotations

import logging
import math
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

FFMPEG = "ffmpeg"


def _run_ffmpeg(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run an ffmpeg command, returning the completed process (no raise)."""
    return subprocess.run(cmd, capture_output=True, text=True)


def format_timestamp(seconds: float) -> str:
    """Format seconds as a WebVTT ``HH:MM:SS.mmm`` timestamp."""
    if seconds < 0:
        seconds = 0.0
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def create_sprite_sheet(
    video_path: Path | str,
    out_path: Path | str,
    interval: float = 2.0,
    cols: int = 5,
    tile_w: int = 160,
    duration: float | None = None,
) -> dict:
    """Build a scrub sprite sheet sampling one frame every ``interval`` seconds.

    ffmpeg filtergraph: ``fps=1/<interval>,scale=<tile_w>:-1,tile=<cols>x<rows>``.
    ``count`` = number of frames ffmpeg's ``fps=1/interval`` filter actually emits
    = ``round(duration/interval)`` (round-half-up) — NOT ``ceil``: ffmpeg samples
    at t=0, interval, 2*interval, …, so a 4.5s clip at interval=2 yields 2 frames,
    not 3. Matching this exactly keeps the WebVTT cue count == the real tile count,
    so no cue points at a blank padding tile. ``rows`` = ``ceil(count/cols)``.

    A sub-interval clip (``count == 0``) and any ffmpeg failure return
    ``sprite_path=None, count=0`` so the caller skips ``write_webvtt`` rather than
    persisting a path to a sheet that was never produced.

    Returns ``{sprite_path, interval, cols, rows, tile_w, tile_h, count}``.
    """
    video_path = Path(video_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    src_w, src_h, probed_dur = _probe_dims_duration(video_path)
    if duration is None:
        duration = probed_dur

    # round-half-up to match ffmpeg's fps=1/interval emission. round() (banker's)
    # diverges at exact half-multiples (round(2.5)=2 but ffmpeg emits 3 at dur=5,
    # interval=2), so use floor(x + 0.5).
    if duration and duration > 0:
        count = math.floor(duration / interval + 0.5)
    else:
        count = 1  # unknown duration: best-effort single frame

    # tile_h preserves the source aspect at the scaled width; ffmpeg's scale=W:-1
    # rounds height to the nearest multiple of 2, so match that here.
    if src_w and src_h:
        tile_h = int(round(tile_w * src_h / src_w))
        tile_h += tile_h % 2
    else:
        tile_h = int(round(tile_w * 9 / 16))
        tile_h += tile_h % 2

    empty = {
        "sprite_path": None,
        "interval": interval,
        "cols": cols,
        "rows": 0,
        "tile_w": tile_w,
        "tile_h": tile_h,
        "count": 0,
    }
    if count <= 0:
        # Sub-interval clip — ffmpeg's fps filter emits no frame; no sheet.
        return empty

    rows = max(1, math.ceil(count / cols))
    cmd = [
        FFMPEG,
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps=1/{interval},scale={tile_w}:-1,tile={cols}x{rows}",
        "-frames:v",
        "1",
        str(out_path),
    ]
    _run_ffmpeg(cmd)

    # Verify ffmpeg actually wrote the sheet (mirror generate_poster's contract):
    # never report success / a sprite_path for a file that does not exist.
    if not (out_path.exists() and out_path.stat().st_size > 0):
        logger.warning("sprite sheet not produced for %s", video_path)
        return empty

    return {
        "sprite_path": str(out_path),
        "interval": interval,
        "cols": cols,
        "rows": rows,
        "tile_w": tile_w,
        "tile_h": tile_h,
        "count": count,
    }


def write_webvtt(
    vtt_path: Path | str,
    sprite_url: str,
    interval: float,
    cols: int,
    tile_w: int,
    tile_h: int,
    count: int,
) -> None:
    """Emit WebVTT scrub cues mapping timeline windows to sprite tiles.

    Cue ``i`` (0-based): ``start = i*interval``, ``end = (i+1)*interval``,
    payload ``<sprite_url>#xywh=<(i%cols)*tile_w>,<(i//cols)*tile_h>,
    <tile_w>,<tile_h>``. The cue spacing is exactly ``interval`` — identical to
    the sprite ``fps=1/interval`` sampling rate (the #1-bug guard).
    """
    vtt_path = Path(vtt_path)
    vtt_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["WEBVTT", ""]
    for i in range(count):
        start = i * interval
        end = (i + 1) * interval  # cue interval == sampling interval (the guard)
        x = (i % cols) * tile_w
        y = (i // cols) * tile_h
        lines.append(f"{format_timestamp(start)} --> {format_timestamp(end)}")
        lines.append(f"{sprite_url}#xywh={x},{y},{tile_w},{tile_h}")
        lines.append("")

    vtt_path.write_text("\n".join(lines), encoding="utf-8")


def _probe_dims_duration(
    video_path: Path,
) -> tuple[int | None, int | None, float | None]:
    """Probe (width, height, duration) for aspect/count — best-effort.

    Returns ``(None, None, None)`` if ffprobe is unavailable or fails; callers
    fall back to a 16:9 tile and a single-frame sheet.
    """
    import json

    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
    except subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError:
        return None, None, None

    streams = data.get("streams") or []
    vs = next((s for s in streams if s.get("codec_type") == "video"), None)
    width = height = None
    if vs is not None:
        try:
            width = int(vs["width"])
            height = int(vs["height"])
        except KeyError, ValueError, TypeError:
            width = height = None
    duration = None
    src = (data.get("format") or {}).get("duration")
    if src is not None:
        try:
            duration = float(src)
        except ValueError, TypeError:
            duration = None
    return width, height, duration
