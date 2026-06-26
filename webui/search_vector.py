"""Vector-store helpers (sqlite-vec) for the search service.

Extracted from ``webui.search`` (pure mechanical move — no behavior change).
``webui.search`` re-exports every symbol defined here, so existing references
such as ``webui.search._vec_rescore`` / ``webui.search.vector_count`` /
``search_svc._assert_image_scope`` keep working unchanged.

These helpers open the pip ``sqlite_vec`` store read-only and per request (the
SQLAlchemy connection in ``pipeline.database`` does NOT load sqlite-vec on this
host). They never write to the DB.
"""

from __future__ import annotations

# --- vec_owner seam (migration 006) ------------------------------------------
# Today the vec store (vec_siglip_1152) is keyed directly by images.id and the
# vec_owner(owner_type, owner_id) map is EMPTY, so every stored vector is an
# image. This ``owner_type`` indirection is the SINGLE place where video-scene
# vectors (D4 / scene-embed-vec_owner) will hook in WITHOUT colliding with image
# ids on the hot read path — the documented reconciliation seam from the roadmap.
# Until scenes embed, "image" is the only wired scope and every vector helper
# below behaves EXACTLY as before. This is intentionally behavior-identical: no
# vec_owner JOIN is added while the map is empty.
OWNER_IMAGE = "image"
OWNER_SCENE = "scene"


def _assert_image_scope(owner_type: str) -> None:
    """Guard the vec helpers' single owner-scope seam.

    Only ``image`` scope is wired today (behavior-identical to the original
    image-keyed path). ``scene`` scope is the explicit D4 hook.
    """
    if owner_type != OWNER_IMAGE:
        # TODO(D4 / scene-embed-vec_owner): when video_scenes embed, resolve vec
        # rows through the vec_owner(owner_type, owner_id) map (migration 006) so
        # scene ids never collide with image ids in vec_siglip_1152. Until then
        # this is the one place that grows a vec_owner JOIN; the image path stays
        # untouched so find-similar/semantic keep their current behavior.
        raise NotImplementedError(
            f"owner_type={owner_type!r} is not wired until scene vectors land "
            "(see vec_owner / D4). Only 'image' scope is supported today."
        )


def vector_count(db) -> int:
    """Number of vectors available in the sqlite-vec rescore table.

    0 => no vectors => vector modes degrade. Opened via the pip sqlite_vec
    loader (the SQLAlchemy connection has no vec extension on this host).
    Returns 0 on any error (missing table / extension) — never raises.
    """
    from pipeline.tier1_embedder import VEC_TABLE, open_vec_db

    conn = None
    try:
        conn = open_vec_db(db.db_path)
        row = conn.execute(f"SELECT COUNT(*) FROM {VEC_TABLE}").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0
    finally:
        if conn is not None:
            conn.close()


def _get_image_vector(
    conn, image_id: int, owner_type: str = OWNER_IMAGE
) -> bytes | None:
    """Raw float32 blob for one image's vector, or None if absent."""
    from pipeline.tier1_embedder import VEC_TABLE

    _assert_image_scope(owner_type)
    row = conn.execute(
        f"SELECT embedding FROM {VEC_TABLE} WHERE image_id = ?", (int(image_id),)
    ).fetchone()
    return row[0] if row else None


def _vec_rescore(
    conn,
    query_blob: bytes,
    allowlist: list[int] | None,
    k: int,
    owner_type: str = OWNER_IMAGE,
) -> list[tuple[int, float]]:
    """Exact sqlite-vec cosine rescore: (image_id, similarity) best-first.

    sqlite-vec ``distance_metric=cosine`` returns a *distance* (0 = identical);
    similarity = 1 - distance. When an allowlist is given the KNN is constrained
    to it (``image_id IN (...)``). ``owner_type`` is the vec_owner seam (D4); only
    ``image`` is wired today and the SQL is unchanged for it.
    """
    from pipeline.tier1_embedder import VEC_TABLE

    _assert_image_scope(owner_type)

    if allowlist is not None:
        if not allowlist:
            return []
        placeholders = ",".join("?" for _ in allowlist)
        sql = (
            f"SELECT image_id, distance FROM {VEC_TABLE} "
            f"WHERE embedding MATCH ? AND k = ? AND image_id IN ({placeholders}) "
            f"ORDER BY distance"
        )
        params = [query_blob, k, *[int(i) for i in allowlist]]
    else:
        sql = (
            f"SELECT image_id, distance FROM {VEC_TABLE} "
            f"WHERE embedding MATCH ? AND k = ? ORDER BY distance"
        )
        params = [query_blob, k]
    rows = conn.execute(sql, params).fetchall()
    return [(int(r[0]), 1.0 - float(r[1])) for r in rows]
