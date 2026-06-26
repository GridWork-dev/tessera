"""Search API routes (contract: docs/specs/backend-search-api.md).

READ-ONLY. Two-stage hybrid (tag pre-filter -> ANN shortlist -> exact rescore
-> optional caption FTS via RRF). Degrades gracefully while Tier 1 embeddings
are not yet populated — see webui/search.py for the full degradation contract.
"""

from __future__ import annotations

import functools

import anyio
from fastapi import APIRouter, HTTPException, Query, Request

from webui import deps
from webui import search as search_svc
from webui.scoping import viewer_owner_id

router = APIRouter()


@router.get("/api/search")
async def api_search(
    request: Request,
    q: str = Query(None, description="free-text query"),
    tags: list[str] = Query(
        default=[], description="repeatable category:value (AND across, OR within)"
    ),
    mode: str = Query("hybrid"),
    rating: str = Query(None),
    label: list[str] = Query(
        default=[], description="repeatable <set>:<value> (AND across, OR within)"
    ),
    person: str = Query(None),
    processed: bool = Query(None, description="filter tagged (true) vs untagged"),
    sort: str = Query("relevance"),
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=200),
):
    """Hybrid search. modes: tags | semantic | text2image | hybrid (default).

    With vectors populated, vector modes rank by SigLIP cosine over a tag-filtered
    allowlist. With NO vectors (current state), semantic/text2image return
    ``vectors_unavailable: true`` (HTTP 200) and hybrid falls back to tag
    relevance. ``tags`` mode always works fully.
    """
    if mode not in search_svc.VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"mode must be one of {search_svc.VALID_MODES}",
        )
    if sort not in search_svc.VALID_SORTS:
        raise HTTPException(
            status_code=422,
            detail=f"sort must be one of {search_svc.VALID_SORTS}",
        )
    try:
        # run_search may run an in-process SigLIP text-tower forward (ADR-0006);
        # offload the synchronous call to a worker thread so the torch embed never
        # blocks the event loop. Behavior is identical to a direct call.
        return await anyio.to_thread.run_sync(
            functools.partial(
                search_svc.run_search,
                deps.db,
                q=q,
                raw_tags=tags,
                mode=mode,
                rating=rating,
                person=person,
                processed=processed,
                sort=sort,
                page=page,
                page_size=page_size,
                viewer_owner_id=viewer_owner_id(request),
                labels=label,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/search/facets")
async def api_search_facets(
    request: Request,
    tags: list[str] = Query(default=[]),
    rating: str = Query(None),
    label: list[str] = Query(default=[]),
    person: str = Query(None),
):
    """Disjunctive facet counts given the current filter (contract shape).

    Distinct from the legacy ``/api/facets`` (which the current SPA consumes):
    this is the filter-aware, disjunctive variant from the search contract —
    ``{categories: {cat: [{value, count}]}, ratings: {..}, people: {..},
    label_facets: {set: {value: count}}}``.
    """
    try:
        facets = search_svc.compute_facets(
            deps.db,
            raw_tags=tags,
            rating=rating,
            person=person,
            viewer_owner_id=viewer_owner_id(request),
        )
        facets["label_facets"] = search_svc.compute_label_facets(
            deps.db,
            labels=label,
            raw_tags=tags,
            rating=rating,
            person=person,
            viewer_owner_id=viewer_owner_id(request),
        )
        return facets
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/images/{image_id}/similar")
async def api_similar(
    request: Request,
    image_id: int,
    k: int = Query(24, ge=1, le=200),
    tags: list[str] = Query(default=[]),
):
    """Similar-by-id via that image's vector -> sqlite-vec rescore.

    Degrades to ``vectors_unavailable: true`` (HTTP 200, empty results) when no
    vectors exist or this image has no vector. 404 if the image id is unknown.
    """
    try:
        result = await anyio.to_thread.run_sync(
            functools.partial(
                search_svc.similar_by_id,
                deps.db,
                image_id,
                k=k,
                raw_tags=tags,
                viewer_owner_id=viewer_owner_id(request),
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result.get("__not_found__"):
        raise HTTPException(status_code=404, detail="Image not found")
    return result
