"""
Pytest fixtures for Lumen Edge Media Pipeline tests.
"""

import os
import sqlite3

# Add project root to path
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.database import Database

_MIG_002 = (
    Path(__file__).parent.parent / "data" / "migrations" / "002_collections_labels.sql"
)
_MIG_013 = Path(__file__).parent.parent / "data" / "migrations" / "013_label_sets.sql"


def add_label_tables(db) -> None:
    """Materialize the migration-only label tables (002 user_labels + 013 sets).

    The SQLAlchemy ``Database`` schema doesn't include user_labels / label_sets /
    label_definitions (they're raw-SQL migrations), so temp-DB tests that exercise
    the Rating label set (Wave 2c) must apply them directly. owner_id is added
    (mirrors migration 012) since LabelStore.assign_label writes it. Idempotent.
    """
    from pipeline.migrations import apply_migration

    conn = sqlite3.connect(db.db_path)
    try:
        apply_migration(conn, _MIG_002)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(user_labels)")}
        if "owner_id" not in cols:
            conn.execute("ALTER TABLE user_labels ADD COLUMN owner_id INTEGER")
            conn.commit()
        apply_migration(conn, _MIG_013)
    finally:
        conn.close()


def assign_rating(db, image_id: int, value: str) -> None:
    """Assign the single-select Rating label (set id 1, seeded by 013) to an image."""
    from pipeline.labels.store import LabelStore

    LabelStore(db.db_path).assign_label(image_id, 1, value)


@pytest.fixture
def temp_db_path():
    """Create a temporary database file path and return it."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


@pytest.fixture
def db(temp_db_path):
    """Create a Database instance connected to a temp file."""
    return Database(temp_db_path)


@pytest.fixture
def session(db):
    """Get a database session for CRUD operations."""
    with db.get_session() as s:
        yield s


@pytest.fixture
def sample_image_data():
    """Minimal valid image data dict for Database.add_image()."""
    return {
        "path": "test_person/test_image.jpg",
        "filename": "test_image.jpg",
        "directory": "test_person",
        "person": "Test Person",
        "file_hash": "abc123def456",
        "width": 1920,
        "height": 1080,
        "filesize": 50000,
        "format": "jpg",
        "created_at": None,
        "modified_at": None,
    }
