"""Preference / active-learning routes (Track 5 scaffold).

Endpoint shapes only — the math lives in pipeline/preference.py and DEGRADES
(insufficient_labels / vectors_unavailable) until the user has flagged
~100 keep + ~100 reject AND the H100 embed run lands. Lazy-imported so main
imports even before the module exists; never fabricates scores.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from pipeline.database import Image
from webui import deps

router = APIRouter()


@router.get("/api/preference/status")
async def preference_status():
    """Label/vector readiness for the preference probe (real counts)."""
    from pipeline import preference

    return preference.preference_status(deps.db)


@router.post("/api/preference/train")
async def preference_train():
    """Train the preference probe. Degrades until enough labels + vectors exist."""
    from pipeline import preference

    return preference.train_probe(deps.db)


@router.post("/api/preference/centroid-preview")
async def preference_centroid_preview(payload: dict):
    """Few-shot centroid (NCM) tag preview over a handful of example ids.

    Body: ``{"positive_ids": [int...], "negative_ids": [int...]?, "threshold": float?}``.
    Degrades to ``vectors_unavailable`` until the corpus is embedded. No writes.
    """
    from pipeline import preference

    positives = payload.get("positive_ids") or []
    negatives = payload.get("negative_ids")
    threshold = payload.get("threshold", 0.2)
    return preference.centroid_preview(
        deps.db, positives, negative_ids=negatives, threshold=threshold
    )


@router.get("/api/preference/ranked")
async def preference_ranked(limit: int = Query(200, ge=1, le=1000)):
    """The sort=preference path. Degrade payload until a probe is trained."""
    from pipeline import preference

    return preference.preference_ranked_ids(deps.db, limit=limit)


def _serialize_image_row(img: Image, rating: str | None = None) -> dict:
    """Image -> the ImageItem dict shape the frontend grid/queue expects.

    Mirrors the /api/images serialization so feed items render identically.
    ``rating`` comes from the Rating label set (Wave 2c — column dropped).
    """
    return {
        "id": img.id,
        "file_hash": img.file_hash,
        "filename": img.filename,
        "person": img.person,
        "width": img.width,
        "height": img.height,
        "rating": rating,
        "processed": img.processed,
        "flagged": bool(img.flagged),
        "flag_action": img.flag_action,
        "tags": [
            {"category": t.category, "value": t.value, "confidence": t.confidence}
            for t in img.tags
        ],
    }


def _images_feed_response(ranked: dict) -> dict:
    """Turn a preference {ok, reason, results:[ids]} into a feed of ImageItems.

    Degrade-first: when ranked.ok is False (no labels/vectors yet — the case
    today), return ``items: []`` plus the real readiness counts so the UI can
    show WHY the feed is empty instead of a misleading 'all clear'.
    """
    from pipeline import preference

    if not ranked.get("ok"):
        return {
            "items": [],
            "degraded": True,
            "reason": ranked.get("reason"),
            "counts": preference.preference_status(deps.db),
        }
    ids = ranked.get("results", [])
    session = deps.db.get_session()
    try:
        from webui import search as search_svc

        by_id = {
            img.id: img for img in session.query(Image).filter(Image.id.in_(ids)).all()
        }
        ratings = search_svc.rating_map_for_ids(session, list(by_id.keys()))
        items = [
            _serialize_image_row(by_id[i], rating=ratings.get(i))
            for i in ids
            if i in by_id
        ]
    finally:
        session.close()
    return {"items": items, "degraded": False}


@router.get("/api/preference/recommend")
async def preference_recommend(limit: int = Query(60, ge=1, le=500)):
    """'More like the keeps' feed for Training mode. Degrades until trained."""
    from pipeline import preference

    return _images_feed_response(preference.preference_ranked_ids(deps.db, limit=limit))


@router.get("/api/preference/edge-cases")
async def preference_edge_cases(limit: int = Query(60, ge=1, le=500)):
    """Uncertainty-sampled 'ask me about edge cases' feed. Degrades until trained."""
    from pipeline import preference

    return _images_feed_response(preference.edge_case_ids(deps.db, limit=limit))
