"""SQLAlchemy ORM models for the media pipeline.

Extracted from ``pipeline.database`` (pure mechanical move — no behavior change).
``pipeline.database`` re-exports every model defined here, so existing imports
like ``from pipeline.database import Image, Tag, ...`` continue to work unchanged.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pipeline.db_base import Base


class User(Base):
    """Application user (multi-user, designed up front — migration 012 / §6).

    First registered user becomes admin (Immich pattern). id=1 is reserved for
    the system/default user that owns all pre-multi-user rows. Password hashing
    lives in ``pipeline.auth`` (vetted KDF — never hand-rolled). The user-data
    tables carry a nullable ``owner_id`` FK back to this table; a NULL owner means
    "legacy/unassigned" and resolves to the sole admin in single-user installs.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user")  # admin | user
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)


class Image(Base):
    """Main image metadata table."""

    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(
        String(1024), unique=True, nullable=False
    )  # relative to content root
    filename: Mapped[str | None] = mapped_column(String(256))
    directory: Mapped[str | None] = mapped_column(String(1024))
    person: Mapped[str | None] = mapped_column(
        String(128)
    )  # Derived from library/<person>/ folder
    file_hash: Mapped[str | None] = mapped_column(
        String(64), unique=True
    )  # content SHA-256
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    filesize: Mapped[int | None] = mapped_column(Integer)
    format: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    modified_at: Mapped[datetime | None] = mapped_column(DateTime)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)

    # Media type. Rating is no longer a column (Wave 2c, migration 016) — it is
    # the removable single-select ``Rating`` label set in user_labels.
    media_type: Mapped[str] = mapped_column(
        String(16), default="image"
    )  # image | video
    processed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Provenance (destructive normalize preserves original identity)
    original_path: Mapped[str | None] = mapped_column(
        String(1024)
    )  # pre-normalize absolute path
    original_filename: Mapped[str | None] = mapped_column(
        String(256)
    )  # pre-normalize filename

    # Stats / moderation
    has_metadata: Mapped[bool] = mapped_column(Boolean, default=False)
    has_thumbnail: Mapped[bool] = mapped_column(Boolean, default=False)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_action: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # reject, maybe, keep

    # NudeNet (Tier 3) — metadata only, NEVER used as a gate.
    # JSON array of {"label": str, "score": float, "box": [x1,y1,x2,y2]}.
    nudenet_regions: Mapped[str | None] = mapped_column(Text)
    nudenet_checked: Mapped[int] = mapped_column(Integer, default=0)

    # Multi-user ownership (migration 012; nullable + additive). NULL == legacy /
    # unassigned, resolves to the sole admin in single-user installs.
    owner_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    # Relationships
    tags = relationship("Tag", back_populates="image", cascade="all, delete-orphan")
    notes = relationship("Notes", back_populates="image", cascade="all, delete-orphan")
    embeddings = relationship(
        "Embedding", back_populates="image", cascade="all, delete-orphan"
    )
    captions = relationship(
        "Caption", back_populates="image", cascade="all, delete-orphan"
    )


class Tag(Base):
    """Tags extracted from VLM analysis."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("images.id"), nullable=False
    )

    # Tag categories (from VLM JSON)
    category: Mapped[str | None] = mapped_column(
        String(32)
    )  # clothing, content_type, setting, etc
    value: Mapped[str | None] = mapped_column(String(256))
    confidence: Mapped[float | None] = mapped_column(Float)
    tag_source: Mapped[str] = mapped_column(
        String(32), default="vlm"
    )  # joytag | wd_eva02 | vlm | openrouter | user
    # Provenance: which model_runs row produced this tag (migration 007). NULL for
    # rows written before the provenance system existed; NOT part of the UNIQUE key.
    run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("model_runs.id"), nullable=True
    )

    # Relationships
    image = relationship("Image", back_populates="tags")

    __table_args__ = (
        # A1 (2026-06-23): tag_source is in the UNIQUE key so WD-EVA02 and JoyTag
        # rows for the same value coexist (cross-model agreement signal). Keep in
        # sync with migrations.migrate_tags_unique_add_source.
        UniqueConstraint(
            "image_id",
            "category",
            "value",
            "tag_source",
            name="uq_tag_image_cat_val_source",
        ),
        {"sqlite_autoincrement": True},
    )


class Embedding(Base):
    """Vector embeddings for similarity search."""

    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("images.id"), nullable=False
    )
    model: Mapped[str | None] = mapped_column(
        String(64)
    )  # siglip-v2, clip-vit-large, etc
    embedding: Mapped[str | None] = mapped_column(
        JSON
    )  # Stored as JSON array of floats
    embedding_blob: Mapped[str | None] = mapped_column(
        Text
    )  # Alternative binary storage for sqlite-vec
    # Provenance (migration 007). The live vector store is vec_siglip_1152 (not
    # this table), so run_id here is for symmetry/future use; the embed run's
    # provenance is recorded as a ModelRun row.
    run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("model_runs.id"), nullable=True
    )

    # Relationships
    image = relationship("Image", back_populates="embeddings")


class Caption(Base):
    """Image captions from Tier-2 VLMs (JoyCaption PyTorch bf16 dedicated)."""

    __tablename__ = "captions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("images.id"), nullable=False
    )
    model: Mapped[str | None] = mapped_column(String(64))
    caption: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(DateTime, default=datetime.now)
    # Provenance: which model_runs row produced this caption (migration 007).
    run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("model_runs.id"), nullable=True
    )

    image = relationship("Image", back_populates="captions")

    __table_args__ = (
        UniqueConstraint("image_id", "model", name="uq_caption_image_model"),
    )


class Video(Base):
    """Video file metadata (migration 006). Separate table from ``images`` — the
    approved design (2026-06-23): video-only columns (duration/fps/codec/sprite/
    vtt) live here; ingest.py must never double-create an ``images`` row for a
    video. Columns mirror data/migrations/006_video_pillar.sql exactly."""

    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str | None] = mapped_column(String(1024))  # relative to content root
    filename: Mapped[str | None] = mapped_column(String(256))
    directory: Mapped[str | None] = mapped_column(String(1024))
    person: Mapped[str | None] = mapped_column(String(128))
    file_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    duration: Mapped[float | None] = mapped_column(Float)  # seconds (ffprobe)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)
    codec: Mapped[str | None] = mapped_column(String(32))
    bitrate: Mapped[int | None] = mapped_column(Integer)
    has_audio: Mapped[int] = mapped_column(Integer, default=0)
    filesize: Mapped[int | None] = mapped_column(Integer)
    poster_path: Mapped[str | None] = mapped_column(String(1024))
    # poster_locked (migration 015): 1 = user pinned this poster; the auto
    # re-picker (repick_posters / smart ingest) leaves locked posters untouched.
    poster_locked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    contact_sheet_path: Mapped[str | None] = mapped_column(String(1024))
    sprite_path: Mapped[str | None] = mapped_column(String(1024))
    vtt_path: Mapped[str | None] = mapped_column(String(1024))
    rating: Mapped[str] = mapped_column(String(16), default="unrated")
    media_type: Mapped[str] = mapped_column(String(16), default="video")
    # 0=not enriched, 1=done, -1=corrupt/unreadable (quarantined, resume key)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str | None] = mapped_column(DateTime, default=datetime.now)
    imported_at: Mapped[str | None] = mapped_column(DateTime, default=datetime.now)
    # Multi-user ownership (migration 012; nullable + additive).
    owner_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    scenes = relationship(
        "VideoScene", back_populates="video", cascade="all, delete-orphan"
    )


class VideoScene(Base):
    """A detected scene within a video (migration 006; PySceneDetect output)."""

    __tablename__ = "video_scenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("videos.id"))
    scene_index: Mapped[int | None] = mapped_column(Integer)
    start_time: Mapped[float | None] = mapped_column(Float)  # seconds
    end_time: Mapped[float | None] = mapped_column(Float)
    keyframe_path: Mapped[str | None] = mapped_column(String(1024))
    caption: Mapped[str | None] = mapped_column(Text)
    processed: Mapped[int] = mapped_column(Integer, default=0)

    video = relationship("Video", back_populates="scenes")


class Notes(Base):
    """Creative planning notes attached to images."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("images.id"), nullable=False
    )
    content: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    # Multi-user ownership (migration 012; nullable + additive).
    owner_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    image = relationship("Image", back_populates="notes")


class Grid(Base):
    """Generated grids of images."""

    __tablename__ = "grids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text)
    layout: Mapped[str | None] = mapped_column(String(32))  # 2x2, 3x3, 4x4, etc
    image_paths: Mapped[str | None] = mapped_column(JSON)  # List of image IDs or paths
    output_path: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[str | None] = mapped_column(DateTime, default=datetime.now)
    query: Mapped[str | None] = mapped_column(Text)  # Query that generated this grid
    # Multi-user ownership (migration 012; nullable + additive).
    owner_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )


class ExclusionRule(Base):
    """Content exclusion rules for filtering images by tag matches."""

    __tablename__ = "exclusion_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(
        String, default="manual"
    )  # 'manual' or 'training'
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    match_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    # Multi-user ownership (migration 012; nullable + additive).
    owner_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (UniqueConstraint("category", "value", name="uq_exclusion_rule"),)


class ModelRun(Base):
    """One batch model run (Tier 0-3), persisting the H100 box's run_manifest.json.

    The base of the provenance system (migration 007): tags/captions/embeddings
    carry a nullable ``run_id`` FK to a row here, so every imported artifact is
    traceable to the run that produced it. ``run_key`` is the manifest's stable
    natural id (upsert key); ``manifest_json`` keeps the full raw manifest so no
    provenance the box emitted is lost even if it isn't promoted to a column.
    """

    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    tier: Mapped[str | None] = mapped_column(String(16))  # tier0..tier3
    model_id: Mapped[str | None] = mapped_column(String(128))
    revision: Mapped[str | None] = mapped_column(String(64))
    precision: Mapped[str | None] = mapped_column(String(16))  # fp16 | fp32
    host: Mapped[str | None] = mapped_column(String(64))
    git_sha: Mapped[str | None] = mapped_column(String(64))
    item_count: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[str | None] = mapped_column(String(32))
    finished_at: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str | None] = mapped_column(String(32), default="complete")
    manifest_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
