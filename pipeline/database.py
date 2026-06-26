"""
Database models and connection for media pipeline.
Uses SQLAlchemy with SQLite and sqlite-vec extension for vector embeddings.

The declarative ``Base`` now lives in ``pipeline.db_base`` and the ORM models in
``pipeline.models``; both are re-exported here so existing imports such as
``from pipeline.database import Base, Image, Tag, ...`` keep working unchanged.
"""

import hashlib
import json
import logging
import os
from typing import Any

from sqlalchemy import (
    create_engine,
    event,
)
from sqlalchemy.orm import (
    Session,
    sessionmaker,
)

from pipeline.db_base import Base
from pipeline.models import (
    Caption,
    Embedding,
    ExclusionRule,
    Grid,
    Image,
    ModelRun,
    Notes,
    Tag,
    User,
    Video,
    VideoScene,
)

__all__ = [
    "Base",
    "Caption",
    "Database",
    "Embedding",
    "ExclusionRule",
    "Grid",
    "Image",
    "ModelRun",
    "Notes",
    "Tag",
    "User",
    "Video",
    "VideoScene",
    "apply_sqlite_pragmas",
    "rebuild_caption_fts",
    "record_model_run",
]

logger = logging.getLogger(__name__)


def apply_sqlite_pragmas(dbapi_connection) -> None:
    """Apply WAL + busy_timeout + synchronous=NORMAL to a raw sqlite connection.

    Applied on EVERY connection (the SQLAlchemy connect-listener, tier1's raw
    sqlite-vec connection, batch_tag's selector connection) so cooperating
    writers share a busy_timeout and the DB stays in WAL. This is the code-level
    fix for the lock-induced corruption seen in the prior backfill (WAL/timeout
    were only ever a session default, never set by code). Idempotent — WAL is a
    persistent DB-level setting; busy_timeout/synchronous are per-connection.
    """
    # journal_mode returns a row ('wal'); fetch it so no result is left pending.
    dbapi_connection.execute("PRAGMA journal_mode=WAL").fetchone()
    dbapi_connection.execute("PRAGMA busy_timeout=5000")
    dbapi_connection.execute("PRAGMA synchronous=NORMAL")


# Fields ModelRun promotes from a run_manifest.json to first-class columns. Any
# other manifest keys are preserved verbatim in manifest_json.
_MODEL_RUN_FIELDS = (
    "tier",
    "model_id",
    "revision",
    "precision",
    "host",
    "git_sha",
    "item_count",
    "started_at",
    "finished_at",
    "status",
)


def record_model_run(
    session: Session, manifest: dict[str, Any], *, tier: str | None = None
) -> ModelRun:
    """Upsert a ModelRun from a run_manifest dict; return the persisted row.

    Idempotent on ``run_key`` (derived from the manifest's ``run_key``/``run_id``/
    ``id`` if present, else from tier+model_id+started_at). Re-recording the same
    run updates the row in place rather than duplicating, so an interrupted import
    can be re-run safely. Tolerant of arbitrary manifest shapes: promotes known
    keys to columns and stores the full manifest in ``manifest_json``.
    """
    m = dict(manifest or {})
    # Set tier BEFORE deriving the key so the tier participates in the composite
    # fallback below.
    if tier is not None:
        m.setdefault("tier", tier)
    run_key = (
        m.get("run_key")
        or m.get("run_id")
        or m.get("id")
        or "|".join(
            str(m.get(k, ""))
            for k in ("tier", "model_id", "started_at")
            if m.get(k) is not None
        )
        or None
    )
    # No identifier in the manifest -> derive a deterministic content key so
    # re-recording the SAME payload upserts instead of duplicating (the docstring's
    # idempotency promise must hold even for an identifier-less manifest).
    if not run_key:
        digest = hashlib.sha256(
            json.dumps(m, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        run_key = f"auto:{digest}"

    existing = session.query(ModelRun).filter(ModelRun.run_key == str(run_key)).first()
    run = existing or ModelRun(run_key=str(run_key))
    for field in _MODEL_RUN_FIELDS:
        if m.get(field) is not None:
            setattr(run, field, m[field])
    run.manifest_json = json.dumps(m, default=str, sort_keys=True)
    if existing is None:
        session.add(run)
    session.flush()  # assign run.id without forcing the caller's commit boundary
    return run


def rebuild_caption_fts(conn) -> int:
    """Repopulate the captions_fts FTS5 index from the captions table.

    Rebuild-after-import (migration 008 rationale): the caption writers use raw
    ``INSERT OR IGNORE`` that bypass SQLAlchemy events, so sync triggers would
    never fire. Call this once after each caption import. Idempotent — a full
    DELETE + INSERT...SELECT, so re-running never duplicates. Accepts a raw
    sqlite3 connection (the importer's) and returns the row count indexed. A
    no-op (returns 0) if the FTS table does not exist yet.
    """
    has_fts = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='captions_fts'"
    ).fetchone()
    if not has_fts:
        return 0
    conn.execute("DELETE FROM captions_fts")
    conn.execute(
        "INSERT INTO captions_fts (rowid, caption, image_id) "
        "SELECT id, caption, image_id FROM captions "
        "WHERE caption IS NOT NULL AND TRIM(caption) != ''"
    )
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM captions_fts").fetchone()[0]


class Database:
    """Database connection and operations."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}")
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Register the connect-listener (sqlite-vec + B2 pragmas) BEFORE
        # create_all, so the very first pooled connection lands in WAL with a
        # busy_timeout rather than the 'delete' journal default.
        self._setup_sqlite_vec()

        # Create tables
        Base.metadata.create_all(self.engine)

    def _setup_sqlite_vec(self):
        """Load sqlite-vec extension."""

        @event.listens_for(self.engine, "connect")
        def connect(dbapi_connection, connection_record):
            try:
                path = "/usr/local/lib/libvec0.dylib"
                if os.path.exists(path):
                    dbapi_connection.execute(f"SELECT load_extension('{path}')")
            except Exception as e:
                logger.warning("Could not load sqlite-vec extension: %s", e)
            # B2: WAL + busy_timeout + synchronous on every connection.
            apply_sqlite_pragmas(dbapi_connection)

    def get_session(self) -> Session:
        """Get database session."""
        return self.SessionLocal()

    def add_image(self, session: Session, image_data: dict[str, Any]) -> Image:
        """Add or update an image record."""
        existing = (
            session.query(Image).filter_by(file_hash=image_data["file_hash"]).first()
        )

        if existing:
            for key, value in image_data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            return existing

        image = Image(**image_data)
        session.add(image)
        return image

    def add_tags(
        self,
        session: Session,
        image_id: int,
        tags_data: dict[str, Any],
        confidence: float = 1.0,
    ):
        """Add tags from VLM analysis. Uses UPSERT to avoid duplicates."""
        from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

        for category, values in tags_data.items():
            if isinstance(values, list):
                for value in values:
                    stmt = (
                        sqlite_upsert(Tag)
                        .values(
                            image_id=image_id,
                            category=category,
                            value=str(value),
                            confidence=confidence,
                            tag_source="vlm",
                        )
                        .on_conflict_do_nothing(
                            index_elements=[
                                "image_id",
                                "category",
                                "value",
                                "tag_source",
                            ]
                        )
                    )
                    session.execute(stmt)
            elif values:
                stmt = (
                    sqlite_upsert(Tag)
                    .values(
                        image_id=image_id,
                        category=category,
                        value=str(values),
                        confidence=confidence,
                        tag_source="vlm",
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            "image_id",
                            "category",
                            "value",
                            "tag_source",
                        ]
                    )
                )
                session.execute(stmt)
        session.commit()

    def add_tags_scored(
        self,
        session: Session,
        image_id: int,
        rows: list[dict[str, Any]],
        run_id: int | None = None,
    ):
        """Add scored tags with explicit per-tag source + confidence.

        Unlike ``add_tags`` (which sets neither ``tag_source`` nor per-tag
        ``confidence``), this writes one Tag per row carrying its own
        ``confidence`` and ``tag_source`` (e.g. ``joytag`` / ``wd_eva02``).
        Each ``row`` is a dict ``{category, value, confidence, tag_source}``.
        Idempotent via UPSERT on (image_id, category, value, tag_source).

        ``run_id`` (migration 007) optionally stamps each tag with the
        ModelRun that produced it. It is provenance only — NOT part of the
        conflict key — so a re-run with the same source still no-ops.
        """
        from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

        for row in rows:
            values = {
                "image_id": image_id,
                "category": row["category"],
                "value": str(row["value"]),
                "confidence": row["confidence"],
                "tag_source": row["tag_source"],
            }
            if run_id is not None:
                values["run_id"] = run_id
            stmt = (
                sqlite_upsert(Tag)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=["image_id", "category", "value", "tag_source"]
                )
            )
            session.execute(stmt)
        session.commit()

    def search_by_tags(
        self, session: Session, filters: dict[str, Any], limit: int = 100
    ) -> list[Image]:
        """Search images by tag filters."""
        query = session.query(Image)

        for category, values in filters.items():
            if category == "person":
                query = query.filter(
                    Image.person.in_(values)
                    if isinstance(values, list)
                    else Image.person == values
                )
            else:
                query = query.join(Tag).filter(
                    Tag.category == category,
                    Tag.value.in_(values)
                    if isinstance(values, list)
                    else Tag.value == values,
                )

        return query.limit(limit).all()

    def create_grid(
        self,
        session: Session,
        name: str,
        description: str,
        layout: str,
        image_ids: list[int],
        query: str = "",
    ) -> Grid:
        """Create a grid record."""
        grid = Grid(
            name=name,
            description=description,
            layout=layout,
            image_paths=json.dumps(image_ids),
            query=query,
        )
        session.add(grid)
        return grid
