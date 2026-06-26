"""
Tests for B2 — SQLite connection pragmas (WAL + busy_timeout + synchronous).

The prior backfill corrupted catalog.db; the suspected cause is two cooperating
connections (SQLAlchemy + tier1's raw sqlite-vec connection) writing without a
busy_timeout or WAL set by code. These pragmas must be applied by code on EVERY
connection, not left to a session default.
"""

import sqlite3

import pytest
from sqlalchemy import text

from pipeline.database import Database, apply_sqlite_pragmas


def test_apply_sqlite_pragmas_sets_wal_busy_timeout_synchronous(tmp_path):
    """apply_sqlite_pragmas(conn) puts a raw sqlite3 conn into WAL/5000/NORMAL."""
    conn = sqlite3.connect(str(tmp_path / "x.db"))
    apply_sqlite_pragmas(conn)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
    conn.close()


def test_database_connections_are_wal_with_busy_timeout(temp_db_path):
    """Every SQLAlchemy connection from Database() carries the pragmas."""
    db = Database(temp_db_path)
    with db.engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000
        assert conn.execute(text("PRAGMA synchronous")).scalar() == 1


def test_open_vec_db_carries_pragmas(tmp_path):
    """tier1's separate raw sqlite-vec connection must also get WAL + timeout."""
    pytest.importorskip("sqlite_vec")
    from pipeline.tier1_embedder import open_vec_db

    conn = open_vec_db(tmp_path / "v.db")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    conn.close()
