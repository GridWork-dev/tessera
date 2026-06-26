import sqlite3
from pathlib import Path

from pipeline.migrations import apply_migration

MIG = Path("data/migrations/013_label_sets.sql")


def _seed_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE images (id INTEGER PRIMARY KEY, rating TEXT);
        CREATE TABLE user_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_id INTEGER NOT NULL, category TEXT NOT NULL, value TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')), owner_id INTEGER,
            UNIQUE(image_id, category, value)
        );
        INSERT INTO images (id, rating) VALUES (1,'nsfw'),(2,'sfw'),(3,'unrated'),(4,'suggestive');
        """
    )
    conn.commit()
    return conn


def test_013_creates_tables_seeds_and_backfills(tmp_path):
    conn = _seed_db(tmp_path / "t.db")
    apply_migration(conn, MIG)
    rating = conn.execute(
        "SELECT id, single_select, is_system FROM label_sets WHERE name='Rating'"
    ).fetchone()
    assert rating == (1, 1, 1)
    defs = conn.execute(
        "SELECT value FROM label_definitions WHERE set_id=1 ORDER BY sort_order"
    ).fetchall()
    assert [d[0] for d in defs] == ["unrated", "sfw", "suggestive", "nsfw"]
    # backfill: rows 1,2,4 (the non-unrated), not row 3
    got = conn.execute(
        "SELECT image_id, value FROM user_labels WHERE set_id=1 ORDER BY image_id"
    ).fetchall()
    assert got == [(1, "nsfw"), (2, "sfw"), (4, "suggestive")]


def test_013_is_idempotent(tmp_path):
    conn = _seed_db(tmp_path / "t.db")
    apply_migration(conn, MIG)
    apply_migration(conn, MIG)  # second run must not duplicate
    n = conn.execute("SELECT COUNT(*) FROM user_labels WHERE set_id=1").fetchone()[0]
    assert n == 3
    nsets = conn.execute("SELECT COUNT(*) FROM label_sets").fetchone()[0]
    assert nsets == 1
