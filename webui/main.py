"""
FastAPI web interface for browsing and searching tagged images.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pipeline.database import Database
from pipeline.grid import GridGenerator
from pipeline.settings import settings
from webui import deps
from webui.thumbnail_cache import ThumbnailCache

app = FastAPI(title="Media Pipeline Browser", version="0.1.0")

# Config flows from the typed settings authority (Spec A) — no ad-hoc YAML read.

# Auto-migrate-with-backup boot hook (Spec C). No-op unless
# MEDIA_PIPELINE_AUTO_MIGRATE is set, so importing this module in tests never
# mutates a DB; fail-closed (raises) on any migration error in production.
from pipeline import bootstrap  # noqa: E402

bootstrap.boot()

# Per-request auth gate (Spec B / §6). Opt-in: a pure pass-through under the
# default dev config (no admin password, loopback bind), enforcing only when
# auth is enabled — so the existing suite needs no auth headers.
from webui.auth_routes import AuthGateMiddleware  # noqa: E402
from webui.auth_routes import router as auth_router  # noqa: E402

app.add_middleware(AuthGateMiddleware)

# CORS (origins from settings.cors_origins; do not hardcode)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

db_path = settings.database_path
db = Database(str(db_path))

# Setup static files
static_dir = Path(__file__).parent / "static"

# Grid generator
grid_gen = GridGenerator()

# Initialize thumbnail cache
cache_dir = settings.thumbs_dir
thumb_cache = ThumbnailCache(cache_dir=cache_dir)

# Bind the shared singletons the split-out route modules read at REQUEST time.
# Called on every (re)import so the test fixtures that pop + re-import webui.main
# rebind these to a fresh temp catalog (D-TEST-DBBIND).
deps.init(database=db, thumbs=thumb_cache, grids=grid_gen)

# --- Platform-evolution wave-2 routers (faces / geo / deep-video / personalize) ---
# Registered before the SPA catch-all; each is inert until its backfill populates data.
from pipeline.personalize.api import (  # noqa: E402
    build_router as build_personalize_router,
)
from webui import (  # noqa: E402
    routes_capabilities,
    routes_collections,
    routes_commerce,
    routes_dashboard,
    routes_exclusions,
    routes_faces,
    routes_geo,
    routes_grids,
    routes_images,
    routes_labels,
    routes_media,
    routes_preference,
    routes_search,
    routes_setup,
    routes_ui_prefs,
    routes_video_deep,
    routes_videos,
)

routes_geo.set_database(db)
app.include_router(auth_router)  # /api/auth/* (login/logout/me/status)
app.include_router(routes_faces.router)  # /api/faces (403 until faces.enabled)
app.include_router(routes_geo.router)  # /api/geo
app.include_router(routes_video_deep.router)  # /api/video-deep
app.include_router(build_personalize_router(db))  # /api/personalize
app.include_router(routes_setup.router)  # /api/setup/* (first-run wizard; Spec F)
app.include_router(routes_commerce.router)  # /api/license + Polar webhook (Spec J)

# --- Split-out per-area route modules (pure extraction from this file). Include
# order is load-bearing: routes_search declares /api/images/{image_id}/similar,
# which must be matched BEFORE routes_images' bare /api/images/{image_id} catch. ---
app.include_router(routes_media.router)
app.include_router(routes_dashboard.router)
app.include_router(routes_search.router)
app.include_router(routes_images.router)
app.include_router(routes_grids.router)
app.include_router(routes_exclusions.router)
app.include_router(routes_collections.router)
app.include_router(routes_videos.router)
app.include_router(routes_preference.router)
app.include_router(routes_ui_prefs.router)  # /api/ui-prefs (UI prefs blob)
app.include_router(routes_labels.router)  # /api/label-sets (user-defined facets)
app.include_router(routes_capabilities.router)  # /api/capabilities (server gates)

# --- Serve built SPA and generated grids (guarded so the test client imports
# even when no frontend build is present). The catch-all below MUST stay last so
# it never shadows /api, /media, /static, /image-content. ---
# The built SPA ships INSIDE the frozen app (PyInstaller datas → sys._MEIPASS),
# which is app payload, not user data. project_root points at the data dir (no
# frontend/dist there), so resolve the SPA from the bundle when frozen and fall
# back to project_root in dev/source runs.
if getattr(sys, "frozen", False):
    _spa_base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
else:
    _spa_base = settings.project_root
_dist = _spa_base / "frontend" / "dist"
_grids = settings.grids_dir
if _grids.exists():
    app.mount("/static/grids", StaticFiles(directory=str(_grids)), name="grids")
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")

    # Backend route prefixes that must NEVER fall through to the SPA. An
    # *unmatched* path under one of these (typo, removed route, bad id form) is a
    # genuine 404 — returning index.html with 200 would mask API errors as HTML.
    _RESERVED_PREFIXES = ("api/", "media/", "static/", "image-content/", "assets/")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # SPA history fallback. Registered LAST so it never shadows a *defined*
        # /api, /media, /static, /image-content route. But unmatched paths under
        # those prefixes must 404 rather than silently serve the SPA shell.
        if full_path.startswith(_RESERVED_PREFIXES):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(str(_dist / "index.html"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.webui_host, port=settings.webui_port)
