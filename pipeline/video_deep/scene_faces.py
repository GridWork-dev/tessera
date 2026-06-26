"""Scene face-detect hand-off seam (for the faces lane to consume LATER).

This lane DETECTS faces on the scene keyframe and writes the bbox + a cropped
face image; the faces lane (``pipeline/faces/``) later embeds + clusters those
crops. Neither package imports the other — the ``scene_faces`` table + the crop
files ARE the contract. We deliberately store only bbox/score/crop_path here (no
embedding, no person link); ``scene_faces.embedded`` is the resume key the faces
lane flips once it has consumed a row.

Detection reuses the compute seam's ``DETECT`` output shape (``Regions`` =
``[{"label","score","box":[x1,y1,x2,y2]}]``), filtered to face labels. This keeps
the seam the single integration point: when a real face detector is wired behind
``DETECT`` (Lane A), its regions flow straight through ``detect_scene_faces``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from pipeline.paths import content_root, relative_to_content, resolve_image_path

logger = logging.getLogger(__name__)

# Default region labels that denote a face. A NudeNet detector emits FACE_F /
# FACE_M; a dedicated face detector emits "face". Case-insensitive match.
FACE_LABELS = ("face", "face_f", "face_m")

CROP_SUBDIR = "_scene_faces"


def detect_scene_faces(
    regions: list[dict[str, Any]], face_labels: tuple[str, ...] = FACE_LABELS
) -> list[dict[str, Any]]:
    """Filter seam ``DETECT`` regions down to face boxes (pure).

    Returns the subset of ``regions`` whose ``label`` (case-insensitive) is in
    ``face_labels``. Dep-free so it unit-tests without any detector. Order is
    preserved (becomes the per-scene ``face_index``).
    """
    wanted = {lbl.lower() for lbl in face_labels}
    return [
        r for r in regions if str(r.get("label", "")).lower() in wanted and r.get("box")
    ]


def crop_face(
    keyframe_path: Path | str, box: list[float], out_path: Path | str
) -> bool:
    """Crop ``box`` ``[x1,y1,x2,y2]`` from the keyframe to ``out_path`` (JPEG).

    Lazy-imports PIL. Clamps the box to the image bounds. Creates the parent dir.
    Returns ``True`` iff a non-empty crop was written; never raises on a bad box
    or a missing keyframe (returns ``False``).
    """
    try:
        from PIL import Image  # lazy
    except ImportError:  # pragma: no cover
        logger.warning("Pillow not installed; cannot crop scene face")
        return False

    keyframe_path = Path(keyframe_path)
    out_path = Path(out_path)
    if not keyframe_path.exists() or not box or len(box) < 4:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(keyframe_path) as img:
            img = img.convert("RGB")
            w, h = img.size
            x1, y1, x2, y2 = (int(round(v)) for v in box[:4])
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                return False
            img.crop((x1, y1, x2, y2)).save(out_path, "JPEG", quality=92)
    except (OSError, ValueError) as exc:
        logger.warning("face crop failed for %s: %s", keyframe_path, exc)
        return False
    return out_path.exists() and out_path.stat().st_size > 0


def persist_scene_faces(
    conn,
    scene_id: int,
    keyframe_rel_path: str,
    faces: list[dict[str, Any]],
    *,
    detector: str,
    crop_root: Path | None = None,
) -> int:
    """Crop each face + write ``scene_faces`` rows; return rows written.

    Idempotent: deletes existing ``scene_faces`` rows for ``scene_id`` first
    (re-run safe), then writes one row per face with ``embedded=0`` (the faces
    lane's pending flag). Crops are stored RELATIVE to the content root. ``conn``
    is a raw sqlite3 connection; the caller commits. A face whose crop fails is
    still recorded (bbox/score) with ``crop_path=NULL`` so the detection isn't
    lost — the faces lane can re-crop from the keyframe.
    """
    conn.execute("DELETE FROM scene_faces WHERE scene_id = ?", (int(scene_id),))
    if not faces:
        return 0

    keyframe_abs = resolve_image_path(keyframe_rel_path)
    root = crop_root if crop_root is not None else content_root() / CROP_SUBDIR
    now = datetime.now().isoformat()
    written = 0
    for face_index, face in enumerate(faces):
        box = face.get("box") or []
        crop_rel: str | None = None
        crop_abs = root / f"{scene_id}_{face_index}.jpg"
        if crop_face(keyframe_abs, box, crop_abs):
            crop_rel = relative_to_content(crop_abs)
        conn.execute(
            "INSERT INTO scene_faces "
            "(scene_id, face_index, bbox, score, crop_path, detector, embedded, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (
                int(scene_id),
                face_index,
                json.dumps(box),
                float(face.get("score", 0.0) or 0.0),
                crop_rel,
                detector,
                now,
            ),
        )
        written += 1
    return written
