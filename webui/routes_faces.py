"""Faces API — APIRouter (NOT registered in main.py; orchestrator wires it).

People + faces browsing, clustering, name/merge/split, and ERASURE. Every
handler is gated by the off-by-default ``faces.enabled`` switch: when the
feature is dark, ALL endpoints return HTTP 403 (the whole surface is invisible).

The router resolves the catalog DB path the same way ``webui/main.py`` does
(``config.yaml`` -> ``project_root`` + ``database.path``) via a FastAPI
dependency, so tests can override it onto a temp db with migration 009 applied
WITHOUT ever touching the real ``data/catalog.db``.

To register (orchestrator):  ``from webui import routes_faces`` then
``app.include_router(routes_faces.router)`` in ``webui/main.py``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pipeline.faces.cluster import run_clustering
from pipeline.faces.config import faces_config, faces_enabled
from pipeline.faces.store import FaceStore
from webui.auth_routes import require_admin

router = APIRouter(prefix="/api/faces", tags=["faces"])


@lru_cache(maxsize=1)
def _db_path() -> str:
    from pipeline.settings import settings

    return str(settings.database_path)


def get_store() -> FaceStore:
    """Dependency: the face store over the configured catalog db.

    Overridden in tests via ``app.dependency_overrides[get_store]`` so the real
    catalog.db is never touched.
    """
    return FaceStore(_db_path())


def _require_enabled() -> None:
    if not faces_enabled():
        raise HTTPException(
            status_code=403,
            detail="faces feature is disabled (set faces.enabled / MP_FACES_ENABLED)",
        )


# ---- request bodies ------------------------------------------------------- #
class NameBody(BaseModel):
    name: str


class MergeBody(BaseModel):
    source_id: int
    target_id: int


# ---- reads ---------------------------------------------------------------- #
@router.get("/people")
def list_people(store: FaceStore = Depends(get_store)) -> list[dict[str, Any]]:
    _require_enabled()
    return store.list_people()


@router.get("/people/{person_id}/faces")
def person_faces(
    person_id: int, store: FaceStore = Depends(get_store)
) -> list[dict[str, Any]]:
    _require_enabled()
    return store.faces_for_person(person_id)


@router.get("/images/{image_id}/faces")
def image_faces(
    image_id: int, store: FaceStore = Depends(get_store)
) -> list[dict[str, Any]]:
    _require_enabled()
    return store.faces_for_image(image_id)


# ---- clustering ----------------------------------------------------------- #
@router.post("/cluster")
def cluster(store: FaceStore = Depends(get_store)) -> dict[str, Any]:
    _require_enabled()
    cfg = faces_config()
    result = run_clustering(
        store,
        embedder=str(cfg["embedder"]),
        eps=float(cfg["cluster_eps"]),
        min_samples=int(cfg["cluster_min_samples"]),
        algorithm=str(cfg.get("cluster_algorithm", "agglomerative")),
    )
    return {
        "faces_considered": result.faces_considered,
        "clusters_created": result.clusters_created,
        "faces_assigned": result.faces_assigned,
        "noise": result.noise,
    }


# ---- mutations ------------------------------------------------------------ #
@router.post("/people/{person_id}/name")
def name_person(
    person_id: int, body: NameBody, store: FaceStore = Depends(get_store)
) -> dict[str, Any]:
    _require_enabled()
    store.name_person(person_id, body.name)
    return {"ok": True, "person_id": person_id, "name": body.name}


@router.post("/people/merge")
def merge_people(
    body: MergeBody, store: FaceStore = Depends(get_store)
) -> dict[str, Any]:
    _require_enabled()
    store.merge_people(body.source_id, body.target_id)
    return {"ok": True, "merged_into": body.target_id}


@router.post("/faces/{face_id}/split")
def split_face(face_id: int, store: FaceStore = Depends(get_store)) -> dict[str, Any]:
    _require_enabled()
    new_pid = store.split_face(face_id)
    return {"ok": True, "face_id": face_id, "new_person_id": new_pid}


# ---- erasure (BIPA / GDPR Art.9) ------------------------------------------ #
@router.delete("/people/{person_id}")
def delete_person(
    person_id: int,
    store: FaceStore = Depends(get_store),
    _: None = Depends(require_admin),
) -> dict[str, Any]:
    """ERASURE: delete a person AND every one of their face vectors (admin-only)."""
    _require_enabled()
    removed = store.delete_person(person_id)
    return {"ok": True, "person_id": person_id, "faces_removed": removed}


@router.post("/purge")
def purge(
    store: FaceStore = Depends(get_store), _: None = Depends(require_admin)
) -> dict[str, Any]:
    """PANIC: wipe the entire face store (all faces + all people) (admin-only)."""
    _require_enabled()
    removed = store.purge_all_faces()
    return {"ok": True, "faces_removed": removed}
