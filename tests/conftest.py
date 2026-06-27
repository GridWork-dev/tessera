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

# --------------------------------------------------------------------------- #
# CI environment shims (GitHub macOS runners differ from a real dev Mac).      #
# --------------------------------------------------------------------------- #
# 1) The runners expose a Metal device whose MPS shared pool is tiny, so torch
#    model loads OOM. Every embedder picks its device via
#    torch.backends.mps.is_available(); force it False on CI so they use CPU.
if os.environ.get("GITHUB_ACTIONS"):
    try:
        import torch

        torch.backends.mps.is_available = lambda: False  # type: ignore[assignment]
    except Exception:
        pass

# 2) The runners' Python is built WITHOUT loadable-sqlite-extension support, so
#    the sqlite-vec tests cannot run. Skip exactly those (and only those) when
#    the capability is absent — identified by the (file, test) pairs below.
_SQLITE_EXT = hasattr(sqlite3.connect(":memory:"), "enable_load_extension")
_NEEDS_SQLITE_EXT = {
    "test_db_pragmas.py::test_open_vec_db_carries_pragmas",
    "test_review_fixes.py::test_run_gate_zero_probes_is_not_a_pass",
    "test_self_retrieval.py::test_main_synthetic_insufficient_exits_2",
    "test_store_parity.py::test_cli_check_store_parity",
    "test_store_parity.py::test_parity_fails_on_idx_skew",
    "test_store_parity.py::test_parity_fails_when_empty",
    "test_store_parity.py::test_parity_passes_when_counts_match",
    "test_tier1_batched.py::test_batched_embed_unprocessed_checkpoints_every_n",
    "test_tier1_batched.py::test_batched_embed_unprocessed_persists_partial_on_crash",
    "test_tier1_batched.py::test_embed_unprocessed_maps_ids_to_correct_vectors",
    "test_tier1_batched.py::test_embed_unprocessed_ragged_final_batch",
    "test_tier1_checkpoint.py::test_embed_unprocessed_checkpoints_every_n",
    "test_tier1_checkpoint.py::test_embed_unprocessed_persists_partial_on_checkpoint",
    "test_tier1_embedder.py::test_vec_rescore_table_create_and_query",
}


def pytest_collection_modifyitems(config, items):
    if _SQLITE_EXT:
        return
    skip = pytest.mark.skip(
        reason="Python built without loadable sqlite extensions (sqlite-vec)"
    )
    for item in items:
        key = f"{item.path.name}::{getattr(item, 'originalname', None) or item.name}"
        if key in _NEEDS_SQLITE_EXT:
            item.add_marker(skip)


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
