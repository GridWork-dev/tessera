"""
Video ingest — ffprobe metadata + poster frame, resumable batch.

Mirrors ``pipeline/ingest.py`` conventions (sha256 file_hash, person/relative
path derivation, resumable shape) but writes the SEPARATE ``videos`` table — the
approved design (2026-06-23). A video NEVER gets an ``images`` row.

Heavy work is delegated to ffprobe / ffmpeg via thin ``subprocess`` wrappers
(``_run_ffprobe`` / ``_run_ffmpeg``) so tests exercise the real binaries against
a tiny synthesized clip. Paths are stored RELATIVE to the content root via
``pipeline/paths.py`` (never absolute, never exfiltrated).

Resumable (see ``knowledge/patterns/resumable-batch.md``):
``videos.processed`` is the resume key — ``1`` done, ``-1`` quarantined
(corrupt/unreadable). A row already present (by file_hash OR path) is skipped, so
a re-run picks up where a crash left off. Any ffprobe/ffmpeg/parse failure
records ``processed=-1`` and continues — the loop never raises.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from .database import Database, Video
from .paths import VALID_RATINGS, relative_to_content

logger = logging.getLogger(__name__)

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}

# Tools live at /opt/homebrew/bin on this host but are on PATH; use bare names so
# the modules stay portable.
FFPROBE = "ffprobe"
FFMPEG = "ffmpeg"


# --------------------------------------------------------------------------- #
# Thin subprocess wrappers (so tests hit real ffmpeg/ffprobe on a tiny clip).
# --------------------------------------------------------------------------- #
def _run_ffprobe(path: Path) -> dict:
    """Run ffprobe and return parsed ``format`` + ``streams`` JSON.

    Raises ``subprocess.CalledProcessError`` on a non-zero exit and
    ``json.JSONDecodeError`` / ``ValueError`` on unparseable output — callers in
    the ingest loop catch these and quarantine the file.
    """
    cmd = [
        FFPROBE,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def _run_ffmpeg(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run an ffmpeg command, returning the completed process (no raise)."""
    return subprocess.run(cmd, capture_output=True, text=True)


# --------------------------------------------------------------------------- #
# Pure helpers.
# --------------------------------------------------------------------------- #
def _parse_fraction(value: str | None) -> float | None:
    """Parse an ffprobe ``num/den`` frame-rate fraction to a float.

    Guards num/0 and VFR ("0/0"); returns ``None`` when unparseable.
    """
    if not value:
        return None
    try:
        num_s, _, den_s = value.partition("/")
        num = float(num_s)
        den = float(den_s) if den_s else 1.0
        if den == 0.0:
            return None
        return num / den
    except ValueError, TypeError:
        return None


def _rotation_degrees(video_stream: dict) -> int:
    """Extract the rotation (degrees) from a video stream.

    Reads the legacy ``tags.rotate`` and the newer ``side_data_list`` display-
    matrix ``rotation``. Returns the absolute rotation normalized to 0/90/180/270.
    """
    rotate = 0
    tags = video_stream.get("tags") or {}
    if "rotate" in tags:
        try:
            rotate = int(float(tags["rotate"]))
        except ValueError, TypeError:
            rotate = 0
    for side in video_stream.get("side_data_list") or []:
        if "rotation" in side:
            try:
                rotate = int(float(side["rotation"]))
            except ValueError, TypeError:
                pass
    return abs(rotate) % 360


def orientation(width: int | None, height: int | None) -> str:
    """Classify display dimensions as ``portrait`` / ``landscape`` / ``square``.

    Unknown/zero dims default to ``landscape`` (the common case).
    """
    if not width or not height:
        return "landscape"
    if width > height:
        return "landscape"
    if height > width:
        return "portrait"
    return "square"


def probe_video(path: Path | str) -> dict:
    """Probe a video with ffprobe -> normalized metadata dict.

    Keys: ``duration`` (float|None), ``width`` / ``height`` (int|None, DISPLAY
    dims — rotation-normalized), ``fps`` (float|None), ``codec`` (str|None),
    ``bitrate`` (int|None), ``has_audio`` (0/1), ``filesize`` (int).

    Raises if ffprobe fails or output is unparseable; the ingest loop catches and
    quarantines. ``filesize`` comes from ``os.path.getsize`` (always available).
    """
    path = Path(path)
    data = _run_ffprobe(path)

    fmt = data.get("format") or {}
    streams = data.get("streams") or []

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    has_audio = 1 if any(s.get("codec_type") == "audio" for s in streams) else 0

    # Duration: prefer format-level, fall back to the video stream.
    duration: float | None = None
    for source in (fmt.get("duration"), (video_stream or {}).get("duration")):
        if source is not None:
            try:
                duration = float(source)
                break
            except ValueError, TypeError:
                continue

    width: int | None = None
    height: int | None = None
    fps: float | None = None
    codec: str | None = None
    if video_stream is not None:
        try:
            width = int(video_stream["width"])
            height = int(video_stream["height"])
        except KeyError, ValueError, TypeError:
            width = height = None
        codec = video_stream.get("codec_name")
        fps = _parse_fraction(video_stream.get("r_frame_rate"))
        if fps is None:
            fps = _parse_fraction(video_stream.get("avg_frame_rate"))
        # Normalize rotation: ±90/270 swaps stored dims to DISPLAY dims.
        if width and height and _rotation_degrees(video_stream) in (90, 270):
            width, height = height, width

    bitrate: int | None = None
    if fmt.get("bit_rate") is not None:
        try:
            bitrate = int(fmt["bit_rate"])
        except ValueError, TypeError:
            bitrate = None

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "codec": codec,
        "bitrate": bitrate,
        "has_audio": has_audio,
        "filesize": os.path.getsize(path),
    }


def generate_poster(
    path: Path | str,
    out_path: Path | str,
    scale_w: int = 300,
    seek: float = 10.0,
    duration: float | None = None,
) -> bool:
    """Write a poster frame for ``path`` to ``out_path``.

    ``ffmpeg -ss <seek> -i <path> -vf "thumbnail,scale=<scale_w>:-2"
    -frames:v 1 <out>``. The ``thumbnail`` filter picks the least-outlier frame
    in a window (dodges black/title frames). When the probed ``duration`` is
    shorter than ``seek``, the ``-ss`` seek is omitted so the clip still yields a
    frame. Creates the parent directory. Returns ``True`` iff ``out_path`` exists
    and is non-empty.
    """
    path = Path(path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [FFMPEG, "-y"]
    # Strict ``>``: at duration == seek the ``-ss`` lands on/after the last frame
    # and ffmpeg writes nothing, so a clip exactly ``seek`` seconds long would lose
    # its poster. Borderline clips fall through to no-seek, where ``thumbnail``
    # still picks a good frame.
    if duration is None or duration > seek:
        cmd += ["-ss", str(seek)]
    cmd += [
        "-i",
        str(path),
        "-vf",
        f"thumbnail,scale={scale_w}:-2",
        "-frames:v",
        "1",
        str(out_path),
    ]
    _run_ffmpeg(cmd)
    return out_path.exists() and out_path.stat().st_size > 0


# --------------------------------------------------------------------------- #
# Resumable batch driver.
# --------------------------------------------------------------------------- #
def _calculate_hash(filepath: Path) -> str:
    """SHA256 of a file (4 KiB chunks) — same as ingest.py."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _derive_person(rel_path: str) -> str | None:
    """Derive the person slug from the relative path.

    Two layouts yield a person slug (same underscore format as images.person,
    e.g. ``Jane_Doe``):
      * ``library/<person>/...`` — the normalized image/library layout.
      * ``_inbound_videos/<Model>/...`` — the video handoff layout (the model
        folder IS the person). Without this branch every inbound clip ingests
        with person=NULL and the primary video facet is silently dropped.
    Anything else (``_unsorted/...`` etc.) -> None.
    """
    parts = Path(rel_path).parts
    if len(parts) >= 2 and parts[0] in ("library", "_inbound_videos"):
        return parts[1]
    return None


def _derive_rating(rel_path: str) -> str:
    """Derive the rating bucket from the normalized layout, else ``unrated``."""
    parts = Path(rel_path).parts
    # library/<person>/<bucket>/... or _unsorted/<bucket>/...
    bucket = ""
    if len(parts) >= 3 and parts[0] == "library":
        bucket = parts[2]
    elif len(parts) >= 2 and parts[0] == "_unsorted":
        bucket = parts[1]
    return bucket if bucket in VALID_RATINGS else "unrated"


def ingest_videos(
    db: Database,
    content_root: Path | str,
    limit: int | None = None,
    poster_dir: Path | str | None = None,
) -> dict:
    """Walk ``content_root`` and ingest videos into the ``videos`` table.

    For each supported video file:

    * compute the sha256 ``file_hash``;
    * skip (resume) if a ``videos`` row already exists for that hash OR path;
    * probe metadata + generate a poster, then insert a ``Video`` row with the
      RELATIVE path/directory/poster_path, derived person/rating, ``processed=1``;
    * on ANY ffprobe/ffmpeg/parse failure, upsert a row with ``processed=-1``
      (quarantine) and CONTINUE — the loop never raises.

    ``limit`` bounds the number of NEW rows added (resume-skips don't count).
    ``poster_dir`` defaults to ``<content_root>/_posters``; posters are stored
    relative to the content root.

    Returns counts ``{"added", "skipped", "quarantined"}``.
    """
    content_root = Path(content_root)
    poster_root = Path(poster_dir) if poster_dir else content_root / "_posters"

    counts = {"added": 0, "skipped": 0, "quarantined": 0}
    session = db.get_session()
    try:
        for root, _dirs, files in sorted(os.walk(content_root)):
            for name in sorted(files):
                if name.startswith("."):
                    continue
                filepath = Path(root) / name
                if filepath.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
                    continue
                if limit is not None and counts["added"] >= limit:
                    session.commit()
                    return counts

                # Build the row key + base metadata defensively: an unreadable
                # (perm-denied), vanished (deleted between os.walk and hashing), or
                # off-root file must quarantine-or-skip — NEVER abort the whole walk
                # (the resumable contract). _calculate_hash opens the file and
                # relative_to_content can raise ValueError off-root, so both must be
                # guarded, not just the probe/poster step below.
                try:
                    rel_path = relative_to_content(filepath)
                    file_hash = _calculate_hash(filepath)
                except (OSError, ValueError) as exc:
                    logger.warning(
                        "Skipping unreadable/off-root video %s: %s", filepath, exc
                    )
                    counts["quarantined"] += 1
                    continue

                # Resume: already present by hash OR path -> skip.
                existing = (
                    session.query(Video)
                    .filter((Video.file_hash == file_hash) | (Video.path == rel_path))
                    .first()
                )
                if existing is not None:
                    counts["skipped"] += 1
                    continue

                try:
                    created_at = datetime.fromtimestamp(filepath.stat().st_mtime)
                except OSError:
                    created_at = None
                base = {
                    "path": rel_path,
                    "filename": filepath.name,
                    "directory": str(Path(rel_path).parent),
                    "person": _derive_person(rel_path),
                    "file_hash": file_hash,
                    "rating": _derive_rating(rel_path),
                    "media_type": "video",
                    "created_at": created_at,
                    "imported_at": datetime.now(),
                }

                try:
                    meta = probe_video(filepath)
                    poster_abs = poster_root / f"{file_hash[:12]}.jpg"
                    # Smart poster: pick a representative frame instead of the
                    # fixed 10s grab. Lazy import keeps cv2 cost off the hot path
                    # and degrades (best is None) when cv2 / extraction is
                    # unavailable, in which case the fixed-seek call is used.
                    # Scenes aren't known at STAGE 1; the repick_posters backfill
                    # uses them. (Pass None here.)
                    from pipeline.video_thumbnail import pick_best_frame_time

                    best = pick_best_frame_time(
                        str(filepath), meta.get("duration") or 0.0, scenes=None
                    )
                    if best is not None:
                        ok = generate_poster(
                            filepath,
                            poster_abs,
                            seek=best,
                            duration=meta.get("duration"),
                        )
                    else:
                        ok = generate_poster(
                            filepath, poster_abs, duration=meta.get("duration")
                        )
                    poster_rel = relative_to_content(poster_abs) if ok else None
                    video = Video(
                        **base,
                        duration=meta["duration"],
                        width=meta["width"],
                        height=meta["height"],
                        fps=meta["fps"],
                        codec=meta["codec"],
                        bitrate=meta["bitrate"],
                        has_audio=meta["has_audio"],
                        filesize=meta["filesize"],
                        poster_path=poster_rel,
                        processed=1,
                    )
                    session.add(video)
                    session.commit()
                    counts["added"] += 1
                except Exception as exc:  # quarantine — never crash the run.
                    session.rollback()
                    logger.warning("Quarantining video (probe/poster failed): %s", exc)
                    try:
                        filesize = filepath.stat().st_size
                    except OSError:
                        filesize = None
                    session.add(Video(**base, filesize=filesize, processed=-1))
                    session.commit()
                    counts["quarantined"] += 1

        session.commit()
    finally:
        session.close()

    logger.info(
        "Video ingest: %d added, %d skipped, %d quarantined",
        counts["added"],
        counts["skipped"],
        counts["quarantined"],
    )
    return counts
