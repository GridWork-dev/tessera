"""Drive ONE scene keyframe through the compute seam, persist the results.

This is the heart of the deep-video layer: it never loads a model itself — it
asks the ``ComputeDispatcher`` to run each requested capability over the scene
keyframe (exactly as the image pipeline does), then writes the rows:

  EMBED   -> vec_scene_1152 + vec_owner (scene-level vector)
  TAG     -> scene_tags        (Tier-0)
  CAPTION -> scene_captions    (Tier-2, model+run keyed)
  DETECT  -> scene_faces       (faces-lane hand-off; face-filtered regions)

The keyframe is extracted first (idempotent). Resumable: a scene already
``processed=1`` is skipped unless ``force=True``. Privacy: pass ``uncensored=True``
so the dispatcher's gate keeps private scenes off ``hosted-moderated`` backends.

All writes go through the SAME single-writer sqlite connection the caller owns —
the privacy + source-of-truth boundary the master spec calls out.
"""

from __future__ import annotations

import logging
from datetime import datetime

from pipeline.compute.base import Capability, ImageRef
from pipeline.video_deep.keyframe import ensure_scene_keyframe
from pipeline.video_deep.scene_faces import detect_scene_faces, persist_scene_faces
from pipeline.video_deep.vec_scene import (
    ensure_scene_vec_table,
    register_vec_owner,
    upsert_scene_vec,
)

logger = logging.getLogger(__name__)

DEFAULT_CAPS = (
    Capability.EMBED,
    Capability.TAG,
    Capability.CAPTION,
    Capability.DETECT,
)


def _persist_scene_tags(conn, scene_id: int, tagset) -> int:
    """Write scene_tags rows for a TagSet (delete-then-insert, re-run safe)."""
    conn.execute("DELETE FROM scene_tags WHERE scene_id = ?", (int(scene_id),))
    n = 0
    for row in tagset.tags:
        conn.execute(
            "INSERT INTO scene_tags (scene_id, category, value, confidence, "
            "tag_source) VALUES (?, ?, ?, ?, ?)",
            (
                int(scene_id),
                row.get("category"),
                row.get("value"),
                row.get("confidence"),
                row.get("tag_source"),
            ),
        )
        n += 1
    return n


def _persist_scene_caption(conn, scene_id: int, caption, run_id: int | None) -> None:
    """Upsert a scene_captions row (unique on scene_id+model)."""
    conn.execute(
        "INSERT INTO scene_captions (scene_id, model, caption, run_id, created_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(scene_id, model) DO UPDATE SET "
        "caption=excluded.caption, run_id=excluded.run_id, "
        "created_at=excluded.created_at",
        (
            int(scene_id),
            caption.model,
            caption.text,
            run_id,
            datetime.now().isoformat(),
        ),
    )
    # Mirror onto video_scenes.caption (mig 006 convenience column) for the
    # existing video UI, which reads that single field.
    conn.execute(
        "UPDATE video_scenes SET caption = ? WHERE id = ?",
        (caption.text, int(scene_id)),
    )


def process_scene(
    conn,
    dispatcher,
    scene,
    video,
    *,
    caps=DEFAULT_CAPS,
    uncensored: bool = True,
    run_id: int | None = None,
    detector_name: str = "seam_detect",
    force: bool = False,
) -> dict:
    """Run ``caps`` over one scene's keyframe via the dispatcher; persist results.

    ``conn``       — raw sqlite3 connection (single writer; caller commits).
    ``dispatcher`` — a ``ComputeDispatcher`` (resolves+routes backends).
    ``scene``/``video`` — ORM rows (duck-typed; ``scene`` needs ``.id``,
                  ``.scene_index``, ``.start_time``, ``.end_time``,
                  ``.keyframe_path``, ``.processed``).

    Returns a per-capability summary dict. Resumable: returns
    ``{"skipped": True}`` when the scene is already ``processed=1`` and not
    ``force``. Idempotent per capability (every persist is delete/upsert).
    """
    if scene.processed == 1 and not force:
        return {"scene_id": scene.id, "skipped": True}

    keyframe_rel = ensure_scene_keyframe(scene, video)
    if not keyframe_rel:
        logger.warning("no keyframe for scene %s; skipping", scene.id)
        return {"scene_id": scene.id, "skipped": True, "reason": "no_keyframe"}

    # Persist the keyframe path on the scene row (idempotent).
    conn.execute(
        "UPDATE video_scenes SET keyframe_path = ? WHERE id = ?",
        (keyframe_rel, int(scene.id)),
    )

    ref = ImageRef(rel_path=keyframe_rel, image_id=None)
    summary: dict = {"scene_id": scene.id}

    if Capability.EMBED in caps:
        vec = dispatcher.run(Capability.EMBED, [ref], uncensored=uncensored)[0]
        ensure_scene_vec_table(conn)
        upsert_scene_vec(conn, scene.id, vec.values)
        register_vec_owner(conn, scene.id)
        summary["embed_dim"] = vec.dim

    if Capability.TAG in caps:
        tagset = dispatcher.run(Capability.TAG, [ref], uncensored=uncensored)[0]
        summary["tags"] = _persist_scene_tags(conn, scene.id, tagset)

    if Capability.CAPTION in caps:
        caption = dispatcher.run(Capability.CAPTION, [ref], uncensored=uncensored)[0]
        _persist_scene_caption(conn, scene.id, caption, run_id)
        summary["captioned"] = True

    if Capability.DETECT in caps:
        regions = dispatcher.run(Capability.DETECT, [ref], uncensored=uncensored)[0]
        faces = detect_scene_faces(regions.regions)
        summary["faces"] = persist_scene_faces(
            conn, scene.id, keyframe_rel, faces, detector=detector_name
        )

    conn.execute("UPDATE video_scenes SET processed = 1 WHERE id = ?", (int(scene.id),))
    return summary
