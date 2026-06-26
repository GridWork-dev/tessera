"""
FastAPI surface for personalization rungs 1-2.

A ``build_router(db)`` factory returning an ``APIRouter`` so the app's existing
module-level ``db`` (``webui/main.py``) is injected without this module
importing the app. The orchestrator wires it with a single line:

    from pipeline.personalize.api import build_router as build_personalize_router
    app.include_router(build_personalize_router(db))

Endpoints (all backend-only this wave):
  POST /api/personalize/probe/preview          -> probe.preview
  POST /api/personalize/probe/apply            -> probe.apply (dry-run default)
  GET  /api/personalize/active-learning/next   -> active_learning.propose_next
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from pipeline.personalize import active_learning, probe


class ProbePreviewRequest(BaseModel):
    pos_ids: list[int]
    neg_ids: list[int]
    threshold: float = 0.5
    sample: int = 20


class ProbeApplyRequest(BaseModel):
    pos_ids: list[int]
    neg_ids: list[int]
    category: str
    value: str
    threshold: float = 0.5
    confidence: float | None = None
    dry_run: bool = True


def build_router(db: Any) -> APIRouter:
    """Build the personalize router bound to a ``Database`` instance."""
    router = APIRouter(prefix="/api/personalize", tags=["personalize"])

    @router.post("/probe/preview")
    def probe_preview(req: ProbePreviewRequest) -> dict[str, Any]:
        return probe.preview(
            db,
            req.pos_ids,
            req.neg_ids,
            threshold=req.threshold,
            sample=req.sample,
        )

    @router.post("/probe/apply")
    def probe_apply(req: ProbeApplyRequest) -> dict[str, Any]:
        return probe.apply(
            db,
            req.pos_ids,
            req.neg_ids,
            category=req.category,
            value=req.value,
            threshold=req.threshold,
            confidence=req.confidence,
            dry_run=req.dry_run,
        )

    @router.get("/active-learning/next")
    def active_learning_next(
        count: int = Query(20, ge=1, le=200),
    ) -> dict[str, Any]:
        return active_learning.propose_next(db, count=count)

    return router


__all__ = ["ProbeApplyRequest", "ProbePreviewRequest", "build_router"]
