"""Grid montage creation + listing routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException

from pipeline.database import Image
from pipeline.paths import resolve_image_path
from pipeline.settings import settings
from webui import deps

router = APIRouter()


@router.post("/api/grids")
async def create_grid_api(
    image_ids: str = Form(...),
    layout: str = Form("3x3"),
    output_name: str = Form(None),
):
    """Create a grid from selected image IDs."""
    session = deps.db.get_session()
    try:
        try:
            ids = [int(id.strip()) for id in image_ids.split(",") if id.strip()]
        except ValueError:
            raise HTTPException(
                status_code=400, detail="image_ids must be comma-separated integers"
            )

        images = session.query(Image).filter(Image.id.in_(ids)).all()
        if not images:
            raise HTTPException(status_code=400, detail="No valid images")

        image_paths = [resolve_image_path(img.path) for img in images]
        if not output_name:
            output_name = f"grid_{len(ids)}_{layout}.jpg"
        # Sanitize: a user-supplied name must never escape the grids dir.
        output_name = Path(output_name).name

        output_dir = settings.grids_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / output_name

        grid_path = deps.grid_gen.create_grid_montage(
            image_paths, layout=layout, output_path=output_path
        )

        if not grid_path:
            raise HTTPException(status_code=500, detail="Grid creation failed")

        return {
            "success": True,
            "url": f"/static/grids/{output_name}",
        }
    finally:
        session.close()


@router.get("/api/grids")
async def list_grids():
    """List generated grids."""
    grids_dir = settings.grids_dir
    grids = []
    if grids_dir.exists():
        for g in sorted(
            grids_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            grids.append(
                {
                    "name": g.name,
                    "url": f"/static/grids/{g.name}",
                }
            )
    return {"grids": grids}
