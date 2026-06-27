"""
Read-only search retrieval for the rebuilt Browse UI.

Implements the two-stage hybrid design from ``docs/specs/backend-search-api.md``:

    1. Tag pre-filter         -> candidate ``image_id`` set (AND across categories,
                                  OR within a category).
    2. ANN shortlist          -> TurboVec ``search(query_vec, k, allowlist=...)``.
    3. Exact rescore          -> sqlite-vec cosine on the shortlist.
    4. Fuse (optional)        -> caption FTS5 + vector via RRF (k=60).

GRACEFUL DEGRADATION (Tier 1 has not fully run — the ``embeddings`` table is
empty and only a partial set of vectors exists in ``vec_siglip_1152``):

* ``tags`` mode and facets work fully NOW from the ~800k-row ``tags`` table.
* ``semantic`` / ``hybrid`` / ``similar`` detect whether ANY vectors are
  available (``vec_siglip_1152`` row count > 0). With no vectors they degrade:
  ``hybrid`` falls back to tag relevance; ``semantic`` / ``similar`` return an
  HTTP 200 payload carrying ``vectors_unavailable: true`` and empty results.
* ``text2image`` is ADDITIONALLY gated on the SigLIP embedding-space
  self-retrieval check (``knowledge/vendors/siglip-quirks.md``). That gate is
  not yet verified, so ``text2image`` always degrades for now. The code path is
  wired to activate once both vectors exist AND ``TEXT2IMAGE_GATE_PASSED`` flips.

This module never writes to the DB. The SQLAlchemy connection in
``pipeline.database`` does NOT load sqlite-vec on this host (the system dylib is
absent), so all vector queries go through ``pipeline.tier1_embedder.open_vec_db``
(the pip ``sqlite_vec`` loader), opened read-only and per request.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session, joinedload

from pipeline.database import Image, Tag

# Caption FTS5 lane (extracted to webui.search_text) — re-exported so existing
# references (search_svc.CAPTION_FTS_TABLE, webui.search._caption_fts, ...) and
# the orchestration helpers below resolve them from this module's namespace.
from webui.search_text import (  # noqa: F401  (re-export facade)
    CAPTION_FTS_TABLE,
    RRF_K,
    _caption_fts,
    _caption_phrase_match,
    _caption_search,
    _fts_match_query,
)

# Vector-store helpers (extracted to webui.search_vector) — re-exported so the
# scripts importing webui.search._vec_rescore / .vector_count and the tests
# touching ._assert_image_scope keep working, and the orchestration below
# resolves them from this module's namespace.
from webui.search_vector import (  # noqa: F401  (re-export facade)
    OWNER_IMAGE,
    OWNER_SCENE,
    _assert_image_scope,
    _get_image_vector,
    _vec_rescore,
    vector_count,
)

# The SigLIP text tower self-retrieval gate (research/04). Until a real run
# verifies it (re-embed ~20 known images, confirm top match is self ~1.0) and a
# text-tower embedder is wired, text2image must degrade. Env-overridable so the
# path can be exercised once the gate passes without a code edit.
TEXT2IMAGE_GATE_PASSED = os.environ.get("TEXT2IMAGE_GATE_PASSED", "0") == "1"

VALID_MODES = ("tags", "semantic", "text2image", "hybrid", "caption")
VALID_SORTS = (
    "relevance",
    "recent",
    "created",
    "modified",
    "filename",
    "size",
    "random",
)


@dataclass
class ParsedTagFilter:
    """tags=cat:val (repeatable) -> {category: [values]} (AND across, OR within)."""

    by_category: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    @classmethod
    def parse(cls, raw_tags: list[str] | None) -> ParsedTagFilter:
        out: dict[str, list[str]] = defaultdict(list)
        for item in raw_tags or []:
            if not item or ":" not in item:
                # Skip malformed entries rather than 500; validation happens in
                # the route which can choose to 422.
                continue
            category, value = item.split(":", 1)
            category, value = category.strip(), value.strip()
            if category and value:
                out[category].append(value)
        return cls(by_category=out)

    def is_empty(self) -> bool:
        return not self.by_category


def parse_tags_or_raise(raw_tags: list[str] | None) -> ParsedTagFilter:
    """Parse ``tags`` params; raise ValueError on a malformed (non cat:val) entry.

    Empty / missing list is fine. A present-but-malformed entry is a client
    error so the route can surface a 422 instead of silently dropping a filter.
    """
    for item in raw_tags or []:
        if ":" not in item or not item.split(":", 1)[0].strip():
            raise ValueError(f"invalid tag filter {item!r}; expected 'category:value'")
    return ParsedTagFilter.parse(raw_tags)


def parse_labels(raw_labels: list[str] | None) -> dict[str, list[str]]:
    """``label=<set>:<value>`` (repeatable) -> {set_name: [values]}.

    AND across different sets, OR within one set (mirrors the tag-filter shape but
    keyed by label-set NAME, matching user_labels.category). Malformed entries
    (no ':' or blank halves) are skipped rather than raising — a generic listing
    filter should degrade quietly, not 422 the whole page.
    """
    out: dict[str, list[str]] = defaultdict(list)
    for item in raw_labels or []:
        if not item or ":" not in item:
            continue
        set_name, value = item.split(":", 1)
        set_name, value = set_name.strip(), value.strip()
        if set_name and value:
            out[set_name].append(value)
    return dict(out)


def _label_tables_present(session: Session) -> bool:
    """True iff migration 013's label_sets table exists on this connection.

    Lets the listing endpoints stay correct on a temp DB that has not run 013
    (the legacy search_api tests) — label filters/facets simply no-op there.
    """
    row = session.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='label_sets'")
    ).first()
    return row is not None


def _label_match_subquery(
    session: Session, set_name: str, values: list[str], prefix: str = "l0"
):
    """``SELECT image_id FROM user_labels WHERE set name = :set AND value IN(..)``.

    Raw SQL (user_labels/label_sets are migration-only, no SQLAlchemy model).
    Returns a textual subquery usable in ``Image.id.in_(...)``. ``prefix`` makes
    the bound-param names unique so multiple subqueries (AND across sets) in ONE
    query don't collide on ``:lset``/``:lv0`` (last-value-wins corruption).
    """
    placeholders = ", ".join(f":{prefix}v{i}" for i in range(len(values)))
    params: dict[str, str] = {f"{prefix}v{i}": v for i, v in enumerate(values)}
    params[f"{prefix}set"] = set_name
    return text(
        "SELECT ul.image_id FROM user_labels ul "
        "JOIN label_sets ls ON ul.set_id = ls.id "
        f"WHERE ls.name = :{prefix}set AND ul.value IN ({placeholders})"
    ).bindparams(**params)


def rating_map_for_ids(session: Session, ids: list[int]) -> dict[int, str]:
    """``{image_id: rating}`` from the Rating label set (Wave 2c, no column).

    Rating is now just the single-select ``Rating`` label set in ``user_labels``;
    the legacy ``images.rating`` column was dropped (migration 016). Returns an
    empty map when the label tables are absent (a temp DB without migration 013)
    so legacy/transitional callers degrade to "no rating" rather than erroring.
    """
    if not ids or not _label_tables_present(session):
        return {}
    placeholders = ", ".join(f":r{i}" for i in range(len(ids)))
    params: dict[str, int] = {f"r{i}": v for i, v in enumerate(ids)}
    rows = session.execute(
        text(
            "SELECT ul.image_id, ul.value FROM user_labels ul "
            "JOIN label_sets ls ON ul.set_id = ls.id "
            f"WHERE ls.name = 'Rating' AND ul.image_id IN ({placeholders})"
        ).bindparams(**params)
    ).fetchall()
    return {image_id: value for image_id, value in rows}


def _apply_label_filter(query, session: Session, labels: dict[str, list[str]]):
    """AND across sets / OR within a set, over user_labels joined to label_sets.

    Each set contributes an ``Image.id IN (subquery)`` clause. No-op (matches
    nothing for that set) when the label tables are absent — a DB without
    migration 013 has no label assignments anyway.
    """
    if not labels or not _label_tables_present(session):
        return query
    for idx, (set_name, values) in enumerate(labels.items()):
        query = query.filter(
            Image.id.in_(
                _label_match_subquery(session, set_name, values, prefix=f"l{idx}")
            )
        )
    return query


def _candidate_query(
    session: Session,
    tag_filter: ParsedTagFilter,
    rating: str | None,
    person: str | None,
    processed: bool | None = None,
    viewer_owner_id: int | None = None,
    labels: dict[str, list[str]] | None = None,
):
    """Build a SQLAlchemy query over Image.id matching the hard filters.

    AND across categories (each category contributes an EXISTS subquery), OR
    within a category (IN over the values). The legacy ``rating=`` param maps to
    ``label=Rating:<v>`` over ``user_labels`` (Wave 2c — the images.rating column
    was dropped); the machine ``rating`` TAG (WD/VLM provenance) is also matched
    so a rating filter still finds tag-only rows.

    ``processed`` (None | True | False) mirrors /api/images: filter tagged vs
    untagged via the ``images.processed`` resume flag when not None.
    """
    query = session.query(Image.id)

    if person:
        query = query.filter(Image.person == person)

    if processed is not None:
        query = query.filter(Image.processed == processed)

    for category, values in tag_filter.by_category.items():
        sub = session.query(Tag.image_id).filter(
            Tag.category == category, Tag.value.in_(values)
        )
        query = query.filter(Image.id.in_(sub))

    # Generic label filter: AND across sets / OR within a set over user_labels.
    query = _apply_label_filter(query, session, labels or {})

    if rating:
        # Legacy ``rating=`` is equivalent to ``label=Rating:<v>`` (spec 3.5).
        # Match the Rating LABEL row OR the machine ``rating`` tag (WD/VLM
        # provenance) — the images.rating column was dropped in Wave 2c.
        rating_tag = session.query(Tag.image_id).filter(
            Tag.category == "rating", Tag.value == rating
        )
        clause = Image.id.in_(rating_tag)
        if _label_tables_present(session):
            clause = clause | Image.id.in_(
                _label_match_subquery(session, "Rating", [rating], prefix="rat")
            )
        query = query.filter(clause)

    # Per-user row scoping (audit C1): a non-admin viewer sees only their own
    # rows + legacy un-owned (NULL) rows. No-op when viewer_owner_id is None
    # (admin / auth-off) — the default, so existing callers are unchanged.
    if viewer_owner_id is not None:
        query = query.filter(
            or_(Image.owner_id == viewer_owner_id, Image.owner_id.is_(None))
        )

    return query


def serialize_image(
    img: Image,
    score: float | None = None,
    score_parts=None,
    rating: str | None = None,
) -> dict:
    """Image -> result dict matching the contract shape.

    ``rating`` is the human rating from the Rating label set (Wave 2c — the
    images.rating column was dropped). Callers pass it from rating_map_for_ids;
    when absent it falls back to the machine ``rating`` tag (WD/VLM provenance).
    """
    out = {
        "id": img.id,
        "file_hash": img.file_hash,
        "person": img.person,
        "width": img.width,
        "height": img.height,
        "rating": rating
        if rating is not None
        else next((t.value for t in img.tags if t.category == "rating"), None),
        "tags": [
            {"category": t.category, "value": t.value, "confidence": t.confidence}
            for t in img.tags
        ],
    }
    if score is not None:
        out["score"] = round(float(score), 6)
    if score_parts is not None:
        out["score_parts"] = score_parts
    return out


def _load_images(session: Session, ids: list[int]) -> dict[int, Image]:
    """Eager-load Image rows (with tags) for the given ids, keyed by id."""
    if not ids:
        return {}
    rows = (
        session.query(Image)
        .options(joinedload(Image.tags))
        .filter(Image.id.in_(ids))
        .all()
    )
    return {img.id: img for img in rows}


def _paginate(items: list, page: int, page_size: int) -> list:
    start = (page - 1) * page_size
    return items[start : start + page_size]


def run_search(
    db,
    *,
    q: str | None,
    raw_tags: list[str] | None,
    mode: str,
    rating: str | None,
    person: str | None,
    sort: str,
    page: int,
    page_size: int,
    processed: bool | None = None,
    viewer_owner_id: int | None = None,
    labels: list[str] | None = None,
) -> dict:
    """Execute a search and return the contract payload.

    Resolves the effective mode given vector availability + the text2image gate,
    runs the appropriate retrieval, and serializes a paged result set. Read-only.

    ``processed`` (None | True | False) filters tagged vs untagged images via the
    ``images.processed`` flag — mirrors the /api/images semantics so the UI can
    scope a search to either side. Degradation behavior is unaffected.
    """
    tag_filter = parse_tags_or_raise(raw_tags)
    label_filter = parse_labels(labels)
    # ``caption`` is a standalone keyword lane — it needs neither vectors nor the
    # text tower, so skip the vector-availability probe for it (and for tags).
    vectors_ok = mode not in ("tags", "caption") and vector_count(db) > 0

    # A vector RANK from free text needs the SigLIP TEXT tower, which only the
    # vector modes use — and only when vectors exist. Embed the query lazily and
    # ONLY then, reusing the result for the vector path below. tags/caption never
    # touch it, so those lanes stay torch-free: instant in the frozen desktop
    # bundle (which ships no torch) and no needless model load / HF network touch
    # on the server. If the tower can't load, query_vector is None and the vector
    # mode degrades to tag relevance.
    query_vector = _text_query_vector(q) if vectors_ok else None
    can_embed_text = query_vector is not None

    # Resolve the EFFECTIVE mode after degradation. A vector mode degrades to
    # tag relevance unless it can actually form a query vector AND vectors exist
    # (AND, for text2image, the gate passed).
    effective_mode = mode
    degraded_from: str | None = None
    vectors_unavailable = False

    if mode == "text2image":
        if not (TEXT2IMAGE_GATE_PASSED and vectors_ok and can_embed_text):
            degraded_from, vectors_unavailable, effective_mode = (
                "text2image",
                True,
                "tags",
            )
    elif mode == "semantic":
        # Free-text semantic also needs a query vector (text tower). Without one,
        # or without vectors, degrade to tag relevance and flag it.
        if not (vectors_ok and can_embed_text):
            degraded_from, vectors_unavailable, effective_mode = (
                "semantic",
                True,
                "tags",
            )
    elif mode == "hybrid":
        # Hybrid silently falls back to tag relevance — still useful, so it does
        # NOT set vectors_unavailable (no hard failure), only degraded_from.
        if not (vectors_ok and can_embed_text):
            degraded_from, effective_mode = "hybrid", "tags"
    elif mode == "caption":
        # Caption keyword lane needs no vectors/text tower. An empty query has
        # nothing to match, so it behaves like tags mode (recency order over the
        # filtered candidates).
        if not (q and q.strip()):
            effective_mode = "tags"

    with db.get_session() as session:
        candidate_ids = [
            r[0]
            for r in _candidate_query(
                session,
                tag_filter,
                rating,
                person,
                processed,
                viewer_owner_id,
                label_filter,
            ).all()
        ]
        total = len(candidate_ids)

        # --- TAGS / degraded path: order candidates, paginate, serialize ---
        if effective_mode == "tags":
            ordered = _order_tag_candidates(session, candidate_ids, sort)
            page_ids = _paginate(ordered, page, page_size)
            images = _load_images(session, page_ids)
            ratings = rating_map_for_ids(session, page_ids)
            results = [
                serialize_image(images[i], rating=ratings.get(i))
                for i in page_ids
                if i in images
            ]
            payload = {
                "results": results,
                "total": total,
                "page": page,
                "page_size": page_size,
                "mode": effective_mode,
            }
            if vectors_unavailable:
                payload["vectors_unavailable"] = True
            if degraded_from:
                payload["degraded_from"] = degraded_from
            return payload

        # --- CAPTION keyword lane: FTS5 over captions, bm25-ranked, intersected
        # with the tag/rating/person/processed candidate set. No vectors, no text
        # tower. ---
        if effective_mode == "caption":
            ordered = _caption_search(session, q, candidate_ids)
            page_ids = _paginate(ordered, page, page_size)
            images = _load_images(session, page_ids)
            ratings = rating_map_for_ids(session, page_ids)
            results = [
                serialize_image(images[i], rating=ratings.get(i))
                for i in page_ids
                if i in images
            ]
            return {
                "results": results,
                "total": len(ordered),
                "page": page,
                "page_size": page_size,
                "mode": "caption",
            }

        # --- VECTOR path: vectors exist AND a text query vector was formed.
        # (Reached only once a text embedder is wired; until then the modes above
        # degrade and never fall through here.) ---
        qvec = query_vector
        ranked = _vector_search(
            db, session, candidate_ids, qvec, q=q, k=page * page_size
        )
        # Apply RRF fusion with caption FTS for hybrid when an FTS table exists.
        if effective_mode == "hybrid":
            ranked = _fuse_rrf(session, ranked, q, candidate_ids)
        ranked = _paginate(ranked, page, page_size)

        page_ids = [i for i, _ in ranked]
        images = _load_images(session, page_ids)
        ratings = rating_map_for_ids(session, page_ids)
        score_by_id = dict(ranked)
        results = [
            serialize_image(
                images[i],
                score=score_by_id[i],
                score_parts={"vector": round(score_by_id[i], 6)},
                rating=ratings.get(i),
            )
            for i in page_ids
            if i in images
        ]
        return {
            "results": results,
            "total": total,
            "page": page,
            "page_size": page_size,
            "mode": effective_mode,
        }


def _order_tag_candidates(
    session: Session, candidate_ids: list[int], sort: str
) -> list[int]:
    """Order candidate ids for the tag / degraded path.

    relevance (no vectors) == recent here; recent = imported_at desc; random =
    DB-side random over the candidate set; created/modified/filename/size are the
    Wave 2a sort keys. Done in SQL to avoid loading rows. Unknown -> recent.
    """
    if not candidate_ids:
        return []
    q = session.query(Image.id).filter(Image.id.in_(candidate_ids))
    if sort == "random":
        q = q.order_by(func.random())
    elif sort == "created":
        q = q.order_by(Image.created_at.desc(), Image.id.desc())
    elif sort == "modified":
        q = q.order_by(Image.modified_at.desc(), Image.id.desc())
    elif sort == "filename":
        q = q.order_by(Image.filename.asc(), Image.id.asc())
    elif sort == "size":
        q = q.order_by(Image.filesize.desc(), Image.id.desc())
    else:  # relevance / recent / unknown -> most-recent first
        q = q.order_by(Image.imported_at.desc(), Image.id.desc())
    return [r[0] for r in q.all()]


def _text_query_vector(q: str | None):
    """Embed a free-text query via the SigLIP TEXT tower -> float32 blob, or None.

    Returns None for an empty/whitespace query. Otherwise lazily imports the
    in-process text embedder (ADR-0006) — torch/transformers load on first call
    and stay resident — embeds ``q`` to a 1152-dim float32 L2-normalized vector,
    and serializes it to the SAME raw-float32 blob form ``_vector_search`` feeds
    to the sqlite-vec ``MATCH`` parameter (``serialize_float32``).

    Importing torch is kept lazy: the import lives inside this function so a
    text-free request (tags mode, facets, the no-vector degrade paths) never
    pulls in the model. TEXT2IMAGE_GATE_PASSED is NOT consulted here — the gate
    stays in ``run_search``; this only makes ``can_embed_text`` true when a
    non-empty query is given AND the embedder is importable.
    """
    if q is None or not q.strip():
        return None
    try:
        from pipeline.text_embedder import embed_text
        from pipeline.tier1_embedder import serialize_float32

        return serialize_float32(embed_text(q))
    except Exception:
        # Text tower unavailable (e.g. torch isn't bundled in the frozen desktop
        # sidecar, or the model failed to load). Degrade gracefully: callers
        # treat None as "no query vector" and fall back to tag relevance instead
        # of 500-ing the whole search.
        return None


def _vector_search(
    db,
    session: Session,
    candidate_ids: list[int],
    query_blob,
    *,
    q: str | None,
    k: int,
) -> list[tuple[int, float]]:
    """ANN shortlist (TurboVec allowlist) -> exact sqlite-vec cosine rescore.

    Returns [(image_id, similarity)] best-first, constrained to the candidate
    allowlist. Only invoked once a query vector exists (text embedder wired);
    until then ``run_search`` degrades before reaching here. The TurboVec
    shortlist is approximate; the sqlite-vec rescore is the exact float pass.
    """
    from pipeline.tier1_embedder import open_vec_db

    conn = None
    try:
        conn = open_vec_db(db.db_path)
        allow = candidate_ids if candidate_ids else None
        return _vec_rescore(conn, query_blob, allow, k)
    finally:
        if conn is not None:
            conn.close()


def _fuse_rrf(
    session: Session,
    vector_ranked: list[tuple[int, float]],
    q: str | None,
    candidate_ids: list[int],
) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion of the vector ranking with caption FTS5 (k=60).

    RRF score(d) = sum over rankings r of 1/(k + rank_r(d)). When no caption FTS
    table is built (current state — ``CAPTION_FTS_TABLE`` is None) there is only
    the vector ranking, so this returns it unchanged (rank-fused with a single
    list == original order). Wired so adding an FTS table activates fusion.
    """
    if not q or CAPTION_FTS_TABLE is None:
        return vector_ranked

    fts_ranked = _caption_fts(session, q, candidate_ids)
    scores: dict[int, float] = defaultdict(float)
    for rank, (image_id, _s) in enumerate(vector_ranked):
        scores[image_id] += 1.0 / (RRF_K + rank + 1)
    for rank, image_id in enumerate(fts_ranked):
        scores[image_id] += 1.0 / (RRF_K + rank + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def similar_by_id(
    db,
    image_id: int,
    *,
    k: int,
    raw_tags: list[str] | None,
    owner_type: str = OWNER_IMAGE,
    viewer_owner_id: int | None = None,
) -> dict:
    """Similar-by-id via that image's vector -> sqlite-vec rescore.

    Returns the contract result shape. Degrades to ``vectors_unavailable`` (200,
    empty results) when no vectors exist or this image has no vector. ``owner_type``
    is the vec_owner seam (D4); only ``image`` is wired today.
    """
    from pipeline.tier1_embedder import open_vec_db

    _assert_image_scope(owner_type)
    tag_filter = parse_tags_or_raise(raw_tags)

    with db.get_session() as session:
        # Scope the seed lookup too: a non-admin must not pull "similar to" a row
        # they can't see (turns a cross-tenant probe into __not_found__).
        target_q = session.query(Image.id).filter(Image.id == image_id)
        if viewer_owner_id is not None:
            target_q = target_q.filter(
                or_(Image.owner_id == viewer_owner_id, Image.owner_id.is_(None))
            )
        target = target_q.first()
        if target is None:
            return {"__not_found__": True}

        # Compute an allowlist whenever there's a tag filter OR a scoped viewer,
        # so the vector rescore stays within the visible set. Stays None (full,
        # unscoped) only for an admin/auth-off caller with no tag filter.
        allowlist: list[int] | None = None
        if not tag_filter.is_empty() or viewer_owner_id is not None:
            allowlist = [
                r[0]
                for r in _candidate_query(
                    session,
                    tag_filter,
                    rating=None,
                    person=None,
                    viewer_owner_id=viewer_owner_id,
                ).all()
            ]

    if vector_count(db) == 0:
        return {
            "results": [],
            "total": 0,
            "mode": "similar",
            "vectors_unavailable": True,
        }

    conn = None
    try:
        conn = open_vec_db(db.db_path)
        seed = _get_image_vector(conn, image_id)
        if seed is None:
            return {
                "results": [],
                "total": 0,
                "mode": "similar",
                "vectors_unavailable": True,
            }
        # +1 so we can drop the seed itself from the neighbours.
        ranked = _vec_rescore(conn, seed, allowlist, k + 1)
    finally:
        if conn is not None:
            conn.close()

    ranked = [(i, s) for i, s in ranked if i != image_id][:k]
    ids = [i for i, _ in ranked]
    with db.get_session() as session:
        images = _load_images(session, ids)
    score_by_id = dict(ranked)
    results = [
        serialize_image(
            images[i],
            score=score_by_id[i],
            score_parts={"vector": round(score_by_id[i], 6)},
        )
        for i in ids
        if i in images
    ]
    return {"results": results, "total": len(results), "mode": "similar"}


def compute_facets(
    db,
    *,
    raw_tags: list[str] | None,
    rating: str | None,
    person: str | None,
    viewer_owner_id: int | None = None,
) -> dict:
    """Disjunctive facet counts given the current filter.

    For each candidate facet, the count is the result size IF that facet were
    added to the current filter. Disjunctive semantics: a facet WITHIN an
    already-active category does NOT constrain by that category (so the user can
    see sibling values to OR-in), but DOES respect every OTHER active filter.

    Implemented over the candidate id set. Brute-force over ~26k images / ~800k
    tags is tens of ms; migration 005's covering index is a perf nicety, not a
    correctness requirement.
    """
    tag_filter = parse_tags_or_raise(raw_tags)

    with db.get_session() as session:
        # Category value counts: for each category, build the candidate set with
        # that category dropped from the active filter (disjunctive), then count
        # images per value of that category within that base set.
        categories: dict[str, list[dict]] = {}
        all_categories = [
            r[0] for r in session.query(Tag.category).distinct().all() if r[0]
        ]

        for cat in all_categories:
            sub_filter = ParsedTagFilter(
                by_category=defaultdict(
                    list,
                    {c: v for c, v in tag_filter.by_category.items() if c != cat},
                )
            )
            base_ids = [
                r[0]
                for r in _candidate_query(
                    session, sub_filter, rating, person, viewer_owner_id=viewer_owner_id
                ).all()
            ]
            if not base_ids:
                categories[cat] = []
                continue
            rows = (
                session.query(Tag.value, func.count(func.distinct(Tag.image_id)))
                .filter(Tag.category == cat, Tag.image_id.in_(base_ids))
                .group_by(Tag.value)
                .order_by(func.count(func.distinct(Tag.image_id)).desc())
                .all()
            )
            categories[cat] = [
                {"value": v, "count": c} for v, c in rows if v is not None
            ]

        # Ratings facet: count per rating value with rating dropped from filter.
        rating_base = [
            r[0]
            for r in _candidate_query(
                session,
                tag_filter,
                rating=None,
                person=person,
                viewer_owner_id=viewer_owner_id,
            ).all()
        ]
        ratings: dict[str, int] = {}
        if rating_base and _label_tables_present(session):
            # Rating is the Rating label set now (Wave 2c) — count per value over
            # user_labels, not the dropped images.rating column.
            placeholders = ", ".join(f":rf{i}" for i in range(len(rating_base)))
            params: dict[str, int] = {f"rf{i}": v for i, v in enumerate(rating_base)}
            rows = session.execute(
                text(
                    "SELECT ul.value, COUNT(DISTINCT ul.image_id) "
                    "FROM user_labels ul JOIN label_sets ls ON ul.set_id = ls.id "
                    f"WHERE ls.name = 'Rating' AND ul.image_id IN ({placeholders}) "
                    "GROUP BY ul.value"
                ).bindparams(**params)
            ).fetchall()
            ratings = {v: c for v, c in rows if v}

        # People facet: count per person with person dropped from filter.
        people_base = [
            r[0]
            for r in _candidate_query(
                session,
                tag_filter,
                rating,
                person=None,
                viewer_owner_id=viewer_owner_id,
            ).all()
        ]
        people: dict[str, int] = {}
        if people_base:
            rows = (
                session.query(Image.person, func.count(Image.id))
                .filter(Image.id.in_(people_base), Image.person.isnot(None))
                .group_by(Image.person)
                .all()
            )
            people = {p: c for p, c in rows if p}

    return {"categories": categories, "ratings": ratings, "people": people}


def compute_label_facets(
    db,
    *,
    labels: list[str] | None = None,
    raw_tags: list[str] | None = None,
    rating: str | None = None,
    person: str | None = None,
    viewer_owner_id: int | None = None,
) -> dict:
    """Per-label-set disjunctive value counts under the current filter.

    For each label set, count images per value with THAT set's own selection
    dropped from the active filter (so the user can see sibling values to OR in),
    while every OTHER active set/tag/person filter still constrains. Mirrors
    compute_facets' disjunctive semantics. Returns ``{set_name: {value: count}}``.
    Empty when migration 013's tables are absent.
    """
    tag_filter = parse_tags_or_raise(raw_tags)
    label_filter = parse_labels(labels)

    out: dict[str, dict[str, int]] = {}
    with db.get_session() as session:
        if not _label_tables_present(session):
            return out
        set_rows = session.execute(
            text("SELECT id, name FROM label_sets ORDER BY sort_order, id")
        ).fetchall()
        for set_id, set_name in set_rows:
            # Disjunctive: drop this set's selection from the active label filter.
            sub_labels = {s: v for s, v in label_filter.items() if s != set_name}
            base_q = _candidate_query(
                session,
                tag_filter,
                rating if set_name != "Rating" else None,
                person,
                viewer_owner_id=viewer_owner_id,
                labels=sub_labels,
            )
            base_ids = [r[0] for r in base_q.all()]
            counts: dict[str, int] = {}
            if base_ids:
                placeholders = ", ".join(f":i{i}" for i in range(len(base_ids)))
                params: dict[str, int] = {f"i{i}": v for i, v in enumerate(base_ids)}
                params["sid"] = set_id
                rows = session.execute(
                    text(
                        "SELECT ul.value, COUNT(DISTINCT ul.image_id) "
                        "FROM user_labels ul "
                        f"WHERE ul.set_id = :sid AND ul.image_id IN ({placeholders}) "
                        "GROUP BY ul.value"
                    ).bindparams(**params)
                ).fetchall()
                # Every set (including Rating) is label-only now — the
                # images.rating column was dropped in Wave 2c.
                counts = {v: c for v, c in rows}
            out[set_name] = counts
    return out


def compute_video_label_facets(db) -> dict:
    """Per-label-set value counts over user_labels assigned to VIDEO ids.

    user_labels is id-generic (image_id column reused for video ids). Counts are
    global over the video corpus (disjunctive refinement is a follow-up, mirroring
    /api/videos/facets). Empty when migration 013's tables are absent or no video
    has labels. Read-only.
    """
    out: dict[str, dict[str, int]] = {}
    with db.get_session() as session:
        if not _label_tables_present(session):
            return out
        rows = session.execute(
            text(
                "SELECT ls.name, ul.value, COUNT(DISTINCT ul.image_id) "
                "FROM user_labels ul "
                "JOIN label_sets ls ON ul.set_id = ls.id "
                "JOIN videos v ON v.id = ul.image_id "
                "GROUP BY ls.name, ul.value"
            )
        ).fetchall()
        for set_name, value, count in rows:
            out.setdefault(set_name, {})[value] = count
    return out
