"""Tests for the auto-migrate-with-backup boot hook (Spec C) + migration 012.

All against a TEMP sqlite db — never the real catalog.db. No torch / no network.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from pipeline import auth, bootstrap
from pipeline.database import Database
from pipeline.settings import REPO_ROOT


@pytest.fixture
def temp_catalog():
    """A temp DB with ORM tables + the raw-SQL tables (002) so 012 can ALTER them."""
    d = tempfile.mkdtemp()
    db = Path(d) / "catalog.db"
    Database(str(db))  # ORM tables incl. users + owner_id columns
    conn = sqlite3.connect(str(db))
    mig002 = REPO_ROOT / "data" / "migrations" / "002_collections_labels.sql"
    conn.executescript(mig002.read_text())
    conn.commit()
    conn.close()
    yield db
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(str(db) + suffix)
        except OSError:
            pass


def _table_cols(db: Path, table: str) -> set[str]:
    conn = sqlite3.connect(str(db))
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def test_migration_012_adds_users_and_owner_columns(temp_catalog):
    v = bootstrap.run_pending_migrations(temp_catalog, do_backup=False)
    assert v == 16  # user_version ledger stamped to the highest migration

    assert "username" in _table_cols(temp_catalog, "users")
    for tbl in (
        "images",
        "videos",
        "collections",
        "notes",
        "grids",
        "exclusion_rules",
        "user_labels",
    ):
        assert "owner_id" in _table_cols(temp_catalog, tbl), tbl


def test_migration_016_drops_images_rating_column(temp_catalog):
    """After migrating through 016, images has NO rating column (Wave 2c).

    The Rating label set (013) still exists and carries its seeded values; the
    drop is idempotent (re-running the full migration set does not error).
    """
    v = bootstrap.run_pending_migrations(temp_catalog, do_backup=False)
    assert v == 16
    assert "rating" not in _table_cols(temp_catalog, "images")

    conn = sqlite3.connect(str(temp_catalog))
    try:
        # The Rating label set + its values survive the column drop.
        row = conn.execute("SELECT id FROM label_sets WHERE name = 'Rating'").fetchone()
        assert row is not None
        values = {
            r[0]
            for r in conn.execute(
                "SELECT value FROM label_definitions WHERE set_id = ?", (row[0],)
            )
        }
        assert values == {"unrated", "sfw", "suggestive", "nsfw"}
    finally:
        conn.close()

    # Idempotent: a second full run does not re-drop / error and stays at 16.
    v2 = bootstrap.run_pending_migrations(temp_catalog, do_backup=False)
    assert v2 == 16
    assert "rating" not in _table_cols(temp_catalog, "images")


def test_migration_012_seeds_system_user(temp_catalog):
    bootstrap.run_pending_migrations(temp_catalog, do_backup=False)
    conn = sqlite3.connect(str(temp_catalog))
    try:
        rows = conn.execute("SELECT id, username, role FROM users").fetchall()
    finally:
        conn.close()
    assert (1, "system", "admin") in rows


def test_run_pending_migrations_is_idempotent(temp_catalog):
    v1 = bootstrap.run_pending_migrations(temp_catalog, do_backup=False)
    v2 = bootstrap.run_pending_migrations(temp_catalog, do_backup=False)
    assert v1 == v2 == 16


def test_user_version_ledger_refuses_downgrade(temp_catalog):
    bootstrap.run_pending_migrations(temp_catalog, do_backup=False)
    # Stamp the DB as newer than this build knows about.
    conn = sqlite3.connect(str(temp_catalog))
    conn.execute("PRAGMA user_version = 999")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="NEWER"):
        bootstrap.run_pending_migrations(temp_catalog, do_backup=False)


def test_seed_admin_creates_and_updates(temp_catalog, monkeypatch):
    bootstrap.run_pending_migrations(temp_catalog, do_backup=False)
    monkeypatch.setenv("MEDIA_PIPELINE_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("MEDIA_PIPELINE_ADMIN_PASSWORD", "first-pw")
    bootstrap.seed_admin(temp_catalog)

    conn = sqlite3.connect(str(temp_catalog))
    row = conn.execute(
        "SELECT password_hash, role FROM users WHERE username = 'admin'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[1] == "admin"
    assert auth.verify_password("first-pw", row[0])

    # Re-seed with a new password: updates in place, no duplicate row.
    monkeypatch.setenv("MEDIA_PIPELINE_ADMIN_PASSWORD", "second-pw")
    bootstrap.seed_admin(temp_catalog)
    conn = sqlite3.connect(str(temp_catalog))
    n = conn.execute("SELECT COUNT(*) FROM users WHERE username='admin'").fetchone()[0]
    row = conn.execute(
        "SELECT password_hash FROM users WHERE username='admin'"
    ).fetchone()
    conn.close()
    assert n == 1
    assert auth.verify_password("second-pw", row[0])


def test_seed_admin_noop_without_password(temp_catalog, monkeypatch):
    bootstrap.run_pending_migrations(temp_catalog, do_backup=False)
    monkeypatch.delenv("MEDIA_PIPELINE_ADMIN_PASSWORD", raising=False)
    bootstrap.seed_admin(temp_catalog)  # must not raise
    conn = sqlite3.connect(str(temp_catalog))
    # Only the system user (id=1) — no admin account created.
    usernames = {r[0] for r in conn.execute("SELECT username FROM users")}
    conn.close()
    assert usernames == {"system"}
