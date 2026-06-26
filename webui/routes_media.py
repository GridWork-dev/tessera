"""Media serving routes: static files, image content, thumbnails, full images."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from pipeline.database import Image
from pipeline.paths import resolve_image_path
from webui import deps

router = APIRouter()

# Setup static files
static_dir = Path(__file__).parent / "static"


@router.get("/static/{filepath:path}")
async def serve_static(filepath: str):
    """Serve static files."""
    static_file = static_dir / filepath
    if static_file.exists():
        return FileResponse(static_file)
    raise HTTPException(status_code=404)


@router.get("/image-content/{image_id}")
async def serve_image_content(image_id: int):
    """Serve image content from filesystem."""
    session = deps.db.get_session()
    try:
        image = session.query(Image).filter(Image.id == image_id).first()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")

        image_path = resolve_image_path(image.path)
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="Image file not found")

        # Determine content type
        content_type = "image/jpeg"
        if image_path.suffix.lower() in [".png", ".gif", ".webp", ".bmp"]:
            content_type = f"image/{image_path.suffix.lower()[1:]}"

        return FileResponse(image_path, media_type=content_type)
    finally:
        session.close()


@router.get("/media/thumb/{file_hash}")
async def serve_thumbnail(
    file_hash: str,
    w: int = Query(400),
    h: int = Query(500),
    fit: str = Query("cover"),
):
    """Serve smart-cropped thumbnail by file hash."""
    session = deps.db.get_session()
    try:
        image = session.query(Image).filter(Image.file_hash == file_hash).first()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")

        thumb_path = deps.thumb_cache.get(resolve_image_path(image.path), w, h, fit)
        if not thumb_path:
            raise HTTPException(status_code=500, detail="Failed to generate thumbnail")

        return FileResponse(
            thumb_path,
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )
    finally:
        session.close()


@router.get("/media/full/{file_hash}")
async def serve_full_image(file_hash: str):
    """Serve full-resolution original image by file hash."""
    session = deps.db.get_session()
    try:
        image = session.query(Image).filter(Image.file_hash == file_hash).first()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")

        image_path = resolve_image_path(image.path)
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="Image file not found")

        content_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        ct = content_map.get(image_path.suffix.lower(), "image/jpeg")

        return FileResponse(
            image_path,
            media_type=ct,
            headers={"Cache-Control": "public, max-age=86400", "ETag": file_hash},
        )
    finally:
        session.close()
