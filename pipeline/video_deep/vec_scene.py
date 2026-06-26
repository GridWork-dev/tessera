"""Scene-level SigLIP vectors — a sibling vec table + the ``vec_owner`` map.

The image float-rescore table ``vec_siglip_1152`` is keyed ``image_id INTEGER
PRIMARY KEY``; scene ids would collide with image ids. So scene vectors go into a
separate sqlite-vec table ``vec_scene_1152`` (same 1152-dim, cosine), and each
insert also writes a row into ``vec_owner`` (migration 006) mapping the scene's
vec rowid to ``('scene', scene_id)`` — fulfilling 006's "unify the index across
pillars" intent without overloading ``images.id``.

Import-cheap: ``sqlite_vec`` and ``struct`` are imported lazily inside the
functions that need the extension, so the module imports on a box without
sqlite-vec (pure-logic tests don't touch these).
"""

from __future__ import annotations

import sqlite3
import struct
from typing import Sequence

# Mirrors VEC_TABLE in tier1_embedder but scene-scoped. 1152 = SigLIP SO400M /
# SigLIP2 SO400M hidden size (kept in lockstep with the image table by design).
VEC_SCENE_TABLE = "vec_scene_1152"
SCENE_EMBEDDING_DIM = 1152


def _serialize_float32(values: Sequence[float]) -> bytes:
    """Pack a float vector into the little-endian float32 blob sqlite-vec wants."""
    return struct.pack(f"<{len(values)}f", *(float(v) for v in values))


def ensure_scene_vec_table(
    conn: sqlite3.Connection, dim: int = SCENE_EMBEDDING_DIM
) -> None:
    """Create the scene float vec table if missing (sqlite-vec ``vec0``).

    Separate from ``vec_siglip_1152`` (images) so scene ids never collide with
    image ids. Requires the sqlite-vec extension loaded on ``conn``.
    """
    conn.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS {VEC_SCENE_TABLE} USING vec0(
            scene_id INTEGER PRIMARY KEY,
            embedding float[{dim}] distance_metric=cosine
        )
        """
    )
    conn.commit()


def upsert_scene_vec(
    conn: sqlite3.Connection, scene_id: int, values: Sequence[float]
) -> None:
    """Idempotent insert of one scene embedding (delete-then-insert).

    vec0 rejects duplicate primary keys, so we delete first to keep writes
    rerunnable (mirrors ``tier1_embedder.upsert_vec``).
    """
    blob = _serialize_float32(values)
    conn.execute(f"DELETE FROM {VEC_SCENE_TABLE} WHERE scene_id = ?", (int(scene_id),))
    conn.execute(
        f"INSERT INTO {VEC_SCENE_TABLE} (scene_id, embedding) VALUES (?, ?)",
        (int(scene_id), blob),
    )


def register_vec_owner(conn: sqlite3.Connection, scene_id: int) -> None:
    """Map this scene's vec rowid into ``vec_owner`` as an owner_type='scene' row.

    ``vec_owner`` (migration 006) unifies the vector index across pillars:
    ``(vec_id PK, owner_type, owner_id)``. For scene vectors the natural vec_id is
    the ``scene_id`` itself (the PK in ``vec_scene_1152``). Idempotent: re-running
    upserts the same mapping. Image rows (owner_type='image') are owned by the
    image path and untouched here.
    """
    conn.execute(
        "INSERT OR REPLACE INTO vec_owner (vec_id, owner_type, owner_id) "
        "VALUES (?, 'scene', ?)",
        (int(scene_id), int(scene_id)),
    )
