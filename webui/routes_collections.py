"""Collection CRUD + membership routes (raw-SQL over migration 002 tables)."""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException
from sqlalchemy import text

from webui import deps

router = APIRouter()


# ── Collections ──


@router.post("/api/collections")
async def create_collection(name: str = Form(...), description: str = Form("")):
    """Create a new collection."""
    session = deps.db.get_session()
    try:
        session.execute(
            text("INSERT INTO collections (name, description) VALUES (:name, :desc)"),
            {"name": name, "desc": description},
        )
        session.commit()
        col_id = session.execute(text("SELECT last_insert_rowid()")).scalar()
        return {
            "id": col_id,
            "name": name,
            "description": description,
            "image_count": 0,
        }
    finally:
        session.close()


@router.get("/api/collections")
async def list_collections():
    """List all collections with image counts."""
    session = deps.db.get_session()
    try:
        rows = session.execute(
            text("""
            SELECT c.id, c.name, c.description, c.cover_image_id, c.created_at,
                   COUNT(ci.image_id) as image_count
            FROM collections c
            LEFT JOIN collection_items ci ON ci.collection_id = c.id
            GROUP BY c.id
            ORDER BY c.created_at DESC
        """)
        ).fetchall()
        return {
            "collections": [
                {
                    "id": r[0],
                    "name": r[1],
                    "description": r[2],
                    "cover_image_id": r[3],
                    "created_at": r[4],
                    "image_count": r[5],
                }
                for r in rows
            ]
        }
    finally:
        session.close()


@router.get("/api/collections/{collection_id}")
async def get_collection(collection_id: int):
    """Get collection details with all image IDs."""
    session = deps.db.get_session()
    try:
        col = session.execute(
            text(
                "SELECT id, name, description, cover_image_id, created_at FROM collections WHERE id = :id"
            ),
            {"id": collection_id},
        ).fetchone()
        if not col:
            raise HTTPException(status_code=404, detail="Collection not found")

        items = session.execute(
            text(
                "SELECT image_id, sort_order, added_at FROM collection_items WHERE collection_id = :id ORDER BY sort_order"
            ),
            {"id": collection_id},
        ).fetchall()

        return {
            "id": col[0],
            "name": col[1],
            "description": col[2],
            "cover_image_id": col[3],
            "created_at": col[4],
            "image_ids": [i[0] for i in items],
            "image_count": len(items),
        }
    finally:
        session.close()


@router.post("/api/collections/{collection_id}/items")
async def add_to_collection(collection_id: int, image_id: int = Form(...)):
    """Add an image to a collection."""
    session = deps.db.get_session()
    try:
        # Check collection exists
        col = session.execute(
            text("SELECT id FROM collections WHERE id = :id"), {"id": collection_id}
        ).fetchone()
        if not col:
            raise HTTPException(status_code=404, detail="Collection not found")

        # Insert (ignore dupes)
        session.execute(
            text("""
            INSERT OR IGNORE INTO collection_items (collection_id, image_id, sort_order)
            VALUES (:cid, :iid, (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM collection_items WHERE collection_id = :cid))
        """),
            {"cid": collection_id, "iid": image_id},
        )
        session.commit()

        count = session.execute(
            text("SELECT COUNT(*) FROM collection_items WHERE collection_id = :id"),
            {"id": collection_id},
        ).scalar()
        return {"ok": True, "image_count": count}
    finally:
        session.close()


@router.delete("/api/collections/{collection_id}/items/{image_id}")
async def remove_from_collection(collection_id: int, image_id: int):
    """Remove an image from a collection."""
    session = deps.db.get_session()
    try:
        session.execute(
            text(
                "DELETE FROM collection_items WHERE collection_id = :cid AND image_id = :iid"
            ),
            {"cid": collection_id, "iid": image_id},
        )
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@router.delete("/api/collections/{collection_id}")
async def delete_collection(collection_id: int):
    """Delete a collection and its items."""
    session = deps.db.get_session()
    try:
        session.execute(
            text("DELETE FROM collections WHERE id = :id"), {"id": collection_id}
        )
        session.commit()
        return {"ok": True}
    finally:
        session.close()
