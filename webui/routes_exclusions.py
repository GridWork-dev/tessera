"""Exclusion rule CRUD + mined-suggestion routes."""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Query

from pipeline.database import ExclusionRule, Tag
from webui import deps

router = APIRouter()


# ── Exclusion Rules ──


@router.post("/api/exclusions")
async def create_exclusion(category: str = Form(...), value: str = Form(...)):
    """Create an exclusion rule and return the number of images it hides."""
    session = deps.db.get_session()
    try:
        # Check for duplicate
        existing = (
            session.query(ExclusionRule)
            .filter_by(category=category, value=value)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=409, detail="Exclusion rule already exists for this tag"
            )

        # Count matching images
        match_count = (
            session.query(Tag).filter_by(category=category, value=value).count()
        )

        rule = ExclusionRule(
            category=category,
            value=value,
            source="manual",
            enabled=True,
            match_count=match_count,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)

        return {
            "id": rule.id,
            "category": rule.category,
            "value": rule.value,
            "enabled": rule.enabled,
            "match_count": match_count,
            "created_at": str(rule.created_at) if rule.created_at else None,
        }
    finally:
        session.close()


@router.get("/api/exclusions")
async def list_exclusions():
    """List all exclusion rules grouped by category."""
    session = deps.db.get_session()
    try:
        rules = (
            session.query(ExclusionRule)
            .order_by(ExclusionRule.category, ExclusionRule.value)
            .all()
        )

        # Group by category
        grouped: dict[str, list] = {}
        for r in rules:
            entry = {
                "id": r.id,
                "category": r.category,
                "value": r.value,
                "enabled": r.enabled,
                "match_count": r.match_count,
                "source": r.source,
                "created_at": str(r.created_at) if r.created_at else None,
            }
            if r.category not in grouped:
                grouped[r.category] = []
            grouped[r.category].append(entry)

        return {"rules": grouped, "total": len(rules)}
    finally:
        session.close()


@router.patch("/api/exclusions/{rule_id}")
async def update_exclusion(rule_id: int, enabled: bool = Form(...)):
    """Enable or disable an exclusion rule."""
    session = deps.db.get_session()
    try:
        rule = session.query(ExclusionRule).filter_by(id=rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail="Exclusion rule not found")

        rule.enabled = enabled
        session.commit()

        return {
            "id": rule.id,
            "category": rule.category,
            "value": rule.value,
            "enabled": rule.enabled,
            "match_count": rule.match_count,
        }
    finally:
        session.close()


@router.delete("/api/exclusions/{rule_id}")
async def delete_exclusion(rule_id: int):
    """Delete an exclusion rule."""
    session = deps.db.get_session()
    try:
        rule = session.query(ExclusionRule).filter_by(id=rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail="Exclusion rule not found")

        session.delete(rule)
        session.commit()

        return {"ok": True, "id": rule_id}
    finally:
        session.close()


@router.get("/api/suggestions/exclusions")
async def suggestions_exclusions(min_count: int = Query(3, ge=1, le=100)):
    """Candidate hide rules mined from rejected images' tags + reasons (no H100)."""
    from pipeline import suggestions

    return suggestions.exclusion_candidates(deps.db, min_count=min_count)
