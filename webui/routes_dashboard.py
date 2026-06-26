"""Dashboard / stats / pipeline / system telemetry routes (read-only)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Query, Request
from sqlalchemy import Integer, column, func, select, table

from pipeline.database import Caption, Embedding, Image, Tag
from pipeline.settings import settings
from webui import deps
from webui.scoping import scope_by_owner_via, scope_query

router = APIRouter()

# Lightweight selectable for the Rating label set (user_labels has no ORM model).
# Rating is a label set now (Wave 2c) — joined to aggregate per-group rating
# counts. ``image_id``/``value`` are the only columns the dashboard needs.
_user_labels = table(
    "user_labels", column("image_id"), column("value"), column("set_id")
)
_label_sets = table("label_sets", column("id"), column("name"))
_RatingLabel = (
    select(
        _user_labels.c.image_id.label("image_id"),
        _user_labels.c.value.label("value"),
    )
    .select_from(
        _user_labels.join(_label_sets, _user_labels.c.set_id == _label_sets.c.id)
    )
    .where(_label_sets.c.name == "Rating")
    .subquery("rating_label")
)


@router.get("/api/tags")
async def api_tags(category: str = Query(None)):
    """API endpoint for tags."""
    session = deps.db.get_session()
    try:
        query = session.query(Tag.category, Tag.value)

        if category:
            query = query.filter(Tag.category == category)

        tags = query.distinct().all()

        # Group by category
        result = {}
        for cat, val in tags:
            if cat not in result:
                result[cat] = []
            result[cat].append(val)

        return result
    finally:
        session.close()


@router.get("/api/stats")
async def get_stats(request: Request):
    """Get catalog statistics for dashboard."""
    session = deps.db.get_session()
    try:
        images = scope_query(session.query(Image), Image, request)
        total = images.count()
        processed = images.filter(Image.processed.is_(True)).count()
        flagged = images.filter(Image.flagged.is_(True)).count()
        people = (
            scope_query(session.query(Image.person), Image, request).distinct().count()
        )

        # tag_categories = true COUNT(DISTINCT category) from the tags table, the
        # same signal /api/facets computes (it groups Tag.category). The old code
        # built a Python set from a (category, value) DISTINCT scan — equivalent
        # result, but it materialized ~1.2M rows just to count categories.
        #
        # ROOT CAUSE of the "should be 11, is 3" report: the under-count is in the
        # DATA, not the query. The 11 documented categories (person, clothing,
        # content_type, pose, ...) describe the VLM (Tier 2) tag shape. The active
        # Tier-0 run (WD-EVA02 + JoyTag) writes only 3 categories — `person`,
        # `rating`, and a flat `tags` bucket for every descriptive label — so
        # COUNT(DISTINCT category) is genuinely 3 today. It rises toward 11 as the
        # VLM caption/tag tier populates the fine-grained categories. Counting via
        # SQL keeps this number honest and consistent with the facets sidebar.
        tag_categories = (
            scope_by_owner_via(
                session.query(func.count(func.distinct(Tag.category))),
                Tag.image_id,
                request,
            )
            .filter(Tag.category.isnot(None))
            .scalar()
            or 0
        )

        return {
            "total_images": total,
            "processed_images": processed,
            "processing_pct": round(processed / total * 100, 1) if total > 0 else 0,
            "flagged_count": flagged,
            "people_count": people,
            "tag_categories": tag_categories,
        }
    finally:
        session.close()


@router.get("/api/stats/directories")
async def get_directory_stats(request: Request):
    """Per-person and per-directory aggregate counts for the dashboard.

    GROUP BY person and (separately) directory, returning image/processed/flagged
    counts plus a rating breakdown. Only the person/directory labels already stored
    in the DB are returned — no absolute paths, no filesystem walk. ``directory``
    is the relative directory column the catalog already keeps.
    """
    session = deps.db.get_session()
    try:
        from webui.search import _label_tables_present

        def _agg(group_col):
            base = (
                scope_query(
                    session.query(
                        group_col.label("key"),
                        func.count(Image.id),
                        func.sum(func.cast(Image.processed, Integer)),
                        func.sum(func.cast(Image.flagged, Integer)),
                    ),
                    Image,
                    request,
                )
                .filter(group_col.isnot(None))
                .group_by(group_col)
                .all()
            )
            # Rating breakdown per group. Rating is the Rating label set now
            # (Wave 2c — images.rating column dropped): LEFT JOIN user_labels for
            # the Rating set and treat a missing assignment as "unrated". No-op on
            # a DB without the label tables (migration 013 absent).
            ratings_by_key: dict[str, dict[str, int]] = {}
            if _label_tables_present(session):
                rating_value = func.coalesce(_RatingLabel.c.value, "unrated")
                rating_rows = (
                    scope_query(
                        session.query(group_col, rating_value, func.count(Image.id)),
                        Image,
                        request,
                    )
                    .outerjoin(_RatingLabel, _RatingLabel.c.image_id == Image.id)
                    .filter(group_col.isnot(None))
                    .group_by(group_col, rating_value)
                    .all()
                )
                for key, rating, cnt in rating_rows:
                    ratings_by_key.setdefault(key, {})[rating or "unrated"] = cnt
            return [
                {
                    "key": key,
                    "image_count": total,
                    "processed_count": int(processed or 0),
                    "flagged_count": int(flagged or 0),
                    "ratings": ratings_by_key.get(key, {}),
                }
                for key, total, processed, flagged in base
            ]

        return {
            "by_person": _agg(Image.person),
            "by_directory": _agg(Image.directory),
        }
    finally:
        session.close()


@router.get("/api/facets")
async def get_facets(request: Request):
    """Get facet counts for sidebar filters."""
    session = deps.db.get_session()
    try:
        # People counts
        people_rows = (
            scope_query(
                session.query(Image.person, func.count(Image.id)), Image, request
            )
            .filter(Image.person.isnot(None))
            .group_by(Image.person)
            .all()
        )
        people = {p: c for p, c in people_rows if p}

        # Category counts (tag categories with counts)
        cat_rows = (
            scope_by_owner_via(
                session.query(Tag.category, func.count(Tag.id)), Tag.image_id, request
            )
            .group_by(Tag.category)
            .all()
        )
        categories = {c: cnt for c, cnt in cat_rows if c}

        # Tag value counts per category
        tags_by_cat = {}
        tag_rows = (
            scope_by_owner_via(
                session.query(Tag.category, Tag.value, func.count(Tag.id)),
                Tag.image_id,
                request,
            )
            .group_by(Tag.category, Tag.value)
            .all()
        )
        for cat, val, cnt in tag_rows:
            if cat not in tags_by_cat:
                tags_by_cat[cat] = []
            tags_by_cat[cat].append({"value": val, "count": cnt})

        # Rating values from tags where category='rating'
        ratings = (
            scope_by_owner_via(session.query(Tag.value), Tag.image_id, request)
            .filter(Tag.category == "rating")
            .distinct()
            .all()
        )
        rating_values = [r[0] for r in ratings if r[0]]

        # Flag action counts
        flag_rows = (
            scope_query(
                session.query(Image.flag_action, func.count(Image.id)), Image, request
            )
            .filter(Image.flag_action.isnot(None))
            .group_by(Image.flag_action)
            .all()
        )
        flag_actions = {a: c for a, c in flag_rows if a}

        return {
            "people": people,
            "categories": categories,
            "tags_by_category": tags_by_cat,
            "ratings": rating_values,
            "flag_actions": flag_actions,
        }
    finally:
        session.close()


def _tagger_running() -> bool:
    """Best-effort: is a batch_tag.py process currently running?

    Read-only, never raises. Prefers psutil (cross-platform, no shell); falls
    back to ``pgrep`` if psutil is absent. Returns False on any failure so the
    dashboard degrades to "not running" rather than 500-ing.
    """
    try:
        import psutil

        for proc in psutil.process_iter(["cmdline"]):
            cmdline = proc.info.get("cmdline") or []
            if any("batch_tag.py" in str(part) for part in cmdline):
                return True
        return False
    except ImportError:
        pass
    except Exception:
        return False

    # psutil unavailable — fall back to pgrep (BSD/macOS + Linux).
    try:
        import subprocess

        result = subprocess.run(
            ["pgrep", "-f", "batch_tag.py"],
            capture_output=True,
            timeout=2,
        )
        return result.returncode == 0
    except Exception:
        return False


@router.get("/api/pipeline")
async def get_pipeline(request: Request):
    """Per-tier pipeline progress for the dashboard. Read-only from catalog.db.

    Short read connection (WAL is on, a tag run may be writing). Each tier
    reports coverage against the total image count:

    * tier0_3 — tagging, from ``images.processed`` (the resume flag the batch
      tagger sets per image once its fast tiers complete).
    * tier1   — embeddings, from the ``embeddings`` table row count (0 today;
      TurboVec/sqlite-vec is the real index but this is the schema signal).
    * tier2   — captions, from DISTINCT ``captions.image_id`` (a row per model,
      so distinct-image avoids double counting multi-model captions).
    * tier3   — NudeNet, from ``images.nudenet_checked`` coverage.

    ``running`` is a single best-effort flag (one batch_tag.py process drives the
    per-image fast tiers 0/3), surfaced under each per-image tier.
    """

    def _pct(count: int, total: int) -> float:
        return round(count / total * 100, 1) if total > 0 else 0.0

    session = deps.db.get_session()
    try:
        images = scope_query(session.query(Image), Image, request)
        total = images.count()
        processed = images.filter(Image.processed.is_(True)).count()
        embeddings = scope_by_owner_via(
            session.query(Embedding), Embedding.image_id, request
        ).count()
        # A caption row is unique per (image_id, model); count distinct images so a
        # second model's caption for the same image doesn't inflate coverage.
        captions = scope_by_owner_via(
            session.query(func.count(func.distinct(Caption.image_id))),
            Caption.image_id,
            request,
        ).scalar()
        captions = int(captions or 0)
        nudenet = images.filter(Image.nudenet_checked == 1).count()
    finally:
        session.close()

    running = _tagger_running()

    return {
        "total": total,
        "tier0_3": {
            "processed": processed,
            "total": total,
            "pct": _pct(processed, total),
            "running": running,
        },
        "tier1": {
            "count": embeddings,
            "total": total,
            "pct": _pct(embeddings, total),
        },
        "tier2": {
            "count": captions,
            "total": total,
            "pct": _pct(captions, total),
        },
        "tier3": {
            "count": nudenet,
            "total": total,
            "pct": _pct(nudenet, total),
            "running": running,
        },
    }


@router.get("/api/pipeline/throughput")
async def get_pipeline_throughput(
    request: Request, minutes: int = Query(10, ge=1, le=1440)
):
    """Best-effort recent processing rate for the monitor.

    There is no per-image "processed_at" column, so the best available timestamp
    signal is ``imported_at``. We count images imported in the last N minutes and
    derive a per-minute rate. If no timestamps fall in the window (or the column
    is unpopulated), we return 0 / null gracefully rather than inventing a rate.
    The ``signal`` field names which column drove the estimate so the UI can label
    it honestly as an import rate (not a true tag-throughput) until a processed_at
    timestamp exists.
    """
    session = deps.db.get_session()
    try:
        cutoff = datetime.now() - timedelta(minutes=minutes)
        recent = (
            scope_query(session.query(Image), Image, request)
            .filter(Image.imported_at.isnot(None), Image.imported_at >= cutoff)
            .count()
        )
        latest = scope_query(
            session.query(func.max(Image.imported_at)), Image, request
        ).scalar()
    finally:
        session.close()

    if recent == 0:
        # Nothing derivable in the window — report zero, never fabricate.
        return {
            "window_minutes": minutes,
            "count": 0,
            "per_minute": 0.0,
            "signal": "imported_at",
            "latest_at": str(latest) if latest else None,
        }

    return {
        "window_minutes": minutes,
        "count": recent,
        "per_minute": round(recent / minutes, 2),
        "signal": "imported_at",
        "latest_at": str(latest) if latest else None,
    }


@router.get("/api/system")
async def get_system():
    """Host telemetry for the dashboard. Best-effort, never blocks.

    psutil is optional (declared in requirements.txt); when it is missing the
    response degrades to ``{"available": false}`` plus the values we can read
    from the stdlib (load average, and the batch_tag.py running flag). No
    sampling interval is used (``cpu_percent(interval=None)`` is non-blocking and
    returns the delta since the last call).
    """
    import os

    # Load average is stdlib (Unix) — available with or without psutil.
    load_avg: list[float] | None
    try:
        load_avg = [round(x, 2) for x in os.getloadavg()]
    except OSError, AttributeError:
        load_avg = None

    out: dict = {
        "available": False,
        "load_average": load_avg,
        "tagger_running": _tagger_running(),
    }

    try:
        import psutil
    except ImportError:
        return out

    out["available"] = True

    # Non-blocking CPU: interval=None compares against the previous call.
    out["cpu_percent"] = psutil.cpu_percent(interval=None)
    out["cpu_count"] = psutil.cpu_count(logical=True)
    out["per_cpu_percent"] = psutil.cpu_percent(interval=None, percpu=True)

    vm = psutil.virtual_memory()
    out["virtual_memory"] = {
        "used": vm.used,
        "total": vm.total,
        "pct": vm.percent,
    }

    # Disk usage for the volume holding catalog.db (the data volume).
    try:
        disk = psutil.disk_usage(str(Path(settings.database_path).parent))
        out["disk_usage"] = {
            "free": disk.free,
            "total": disk.total,
            "pct": disk.percent,
        }
    except Exception:
        out["disk_usage"] = None

    # GPU: Apple Silicon has no nvidia-smi. Report MPS availability only if torch
    # is ALREADY imported (cheap) — never import the heavy module just to check.
    torch_mod = sys.modules.get("torch")
    if torch_mod is not None:
        try:
            out["gpu"] = {
                "backend": "mps",
                "available": bool(torch_mod.backends.mps.is_available()),
            }
        except Exception:
            out["gpu"] = None

    return out
