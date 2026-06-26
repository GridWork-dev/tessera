"""Label-sets API — user-defined faceted labels.

All paths live under /api/label-sets to avoid colliding with the legacy
/api/images/{id}/labels EAV in routes_images.py. Mirrors routes_faces' DB-path
dependency so tests override get_store onto a temp DB (never touches catalog.db).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pipeline.labels.store import LabelStore

router = APIRouter(prefix="/api/label-sets", tags=["labels"])


@lru_cache(maxsize=1)
def _db_path() -> str:
    from pipeline.settings import settings

    return str(settings.database_path)


def get_store() -> LabelStore:
    return LabelStore(_db_path())


class SetBody(BaseModel):
    name: str
    single_select: bool = False
    color: str | None = None


class PatchSetBody(BaseModel):
    name: str | None = None
    single_select: bool | None = None
    color: str | None = None
    sort_order: int | None = None


class ValueBody(BaseModel):
    value: str
    color: str | None = None


class AssignBody(BaseModel):
    set_id: int
    value: str


@router.get("")
def list_sets(store: LabelStore = Depends(get_store)) -> list[dict[str, Any]]:
    return store.list_sets()


@router.post("")
def create_set(body: SetBody, store: LabelStore = Depends(get_store)) -> dict[str, Any]:
    sid = store.create_set(body.name, body.single_select, body.color)
    return {"id": sid, "name": body.name, "single_select": body.single_select}


@router.patch("/{set_id}")
def update_set(
    set_id: int, body: PatchSetBody, store: LabelStore = Depends(get_store)
) -> dict[str, Any]:
    store.update_set(
        set_id,
        name=body.name,
        single_select=body.single_select,
        color=body.color,
        sort_order=body.sort_order,
    )
    return {"ok": True, "set_id": set_id}


@router.delete("/{set_id}")
def delete_set(set_id: int, store: LabelStore = Depends(get_store)) -> dict[str, Any]:
    store.delete_set(set_id)
    return {"ok": True, "set_id": set_id}


@router.post("/{set_id}/values")
def add_value(
    set_id: int, body: ValueBody, store: LabelStore = Depends(get_store)
) -> dict[str, Any]:
    vid = store.add_value(set_id, body.value, body.color)
    return {"id": vid, "set_id": set_id, "value": body.value}


@router.delete("/{set_id}/values/{value_id}")
def remove_value(
    set_id: int, value_id: int, store: LabelStore = Depends(get_store)
) -> dict[str, Any]:
    store.remove_value(value_id)
    return {"ok": True, "value_id": value_id}


@router.get("/images/{image_id}")
def image_labels(
    image_id: int, store: LabelStore = Depends(get_store)
) -> list[dict[str, Any]]:
    return store.labels_for_image(image_id)


@router.post("/images/{image_id}")
def assign(
    image_id: int, body: AssignBody, store: LabelStore = Depends(get_store)
) -> dict[str, Any]:
    try:
        lid = store.assign_label(image_id, body.set_id, body.value)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"id": lid, "image_id": image_id, "set_id": body.set_id, "value": body.value}


@router.delete("/images/{image_id}/{label_id}")
def unassign(
    image_id: int, label_id: int, store: LabelStore = Depends(get_store)
) -> dict[str, Any]:
    store.unassign(label_id)
    return {"ok": True, "label_id": label_id}
