"""
Tests for the A1 schema migration — add tag_source to the tags UNIQUE key.

The migration operates on a raw, OLD-schema DB built here (NOT via the SQLAlchemy
model), so it is independent of the model definition. It must:
  * let both WD and JoyTag rows for the same (image, category, value) coexist,
  * preserve every existing row verbatim,
  * be idempotent (2nd run is a no-op),
  * keep the AUTOINCREMENT high-water mark (no id reuse after the table rebuild).
"""

import sqlite3

from pipeline.migrations import (
    migrate_tags_unique_add_source,
    tags_unique_has_source,
)

OLD_TAGS_DDL = """
CREATE TABLE tags (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    category VARCHAR(32),
    value VARCHAR(256),
    confidence FLOAT,
    tag_source TEXT DEFAULT 'vlm',
    CONSTRAINT uq_tag_image_cat_val UNIQUE (image_id, category, value),
    FOREIGN KEY(image_id) REFERENCES images (id)
);
"""


def _make_old_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("CREATE TABLE images (id INTEGER PRIMARY KEY);" + OLD_TAGS_DDL)
    conn.execute("INSERT INTO images (id) VALUES (1)")
    conn.execute(
        "INSERT INTO tags (image_id, category, value, confidence, tag_source) "
        "VALUES (1, 'tags', 'woman', 0.9, 'wd_eva02')"
    )
    conn.commit()
    conn.close()


def test_old_schema_blocks_second_source(tmp_path):
    """Sanity: the OLD 3-col unique collapses the joytag row (the bug we fix)."""
    path = str(tmp_path / "old.db")
    _make_old_db(path)
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT OR IGNORE INTO tags (image_id, category, value, confidence, tag_source) "
        "VALUES (1, 'tags', 'woman', 0.8, 'joytag')"
    )
    conn.commit()
    n = conn.execute(
        "SELECT COUNT(*) FROM tags WHERE image_id=1 AND value='woman'"
    ).fetchone()[0]
    conn.close()
    assert n == 1


def test_tags_unique_has_source_detects_state(tmp_path):
    path = str(tmp_path / "d.db")
    _make_old_db(path)
    conn = sqlite3.connect(path)
    assert tags_unique_has_source(conn) is False
    conn.close()
    migrate_tags_unique_add_source(path)
    conn = sqlite3.connect(path)
    assert tags_unique_has_source(conn) is True
    conn.close()


def test_migration_lets_both_sources_coexist(tmp_path):
    path = str(tmp_path / "m.db")
    _make_old_db(path)
    assert migrate_tags_unique_add_source(path) is True

    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT OR IGNORE INTO tags (image_id, category, value, confidence, tag_source) "
        "VALUES (1, 'tags', 'woman', 0.8, 'joytag')"
    )
    conn.commit()
    rows = conn.execute(
        "SELECT tag_source FROM tags WHERE image_id=1 AND value='woman' "
        "ORDER BY tag_source"
    ).fetchall()
    conn.close()
    assert [r[0] for r in rows] == ["joytag", "wd_eva02"]


def test_migration_preserves_existing_rows(tmp_path):
    path = str(tmp_path / "p.db")
    _make_old_db(path)
    migrate_tags_unique_add_source(path)
    conn = sqlite3.connect(path)
    row = conn.execute(
        "SELECT id, image_id, category, value, confidence, tag_source FROM tags"
    ).fetchall()
    conn.close()
    assert row == [(1, 1, "tags", "woman", 0.9, "wd_eva02")]


def test_migration_idempotent(tmp_path):
    path = str(tmp_path / "i.db")
    _make_old_db(path)
    assert migrate_tags_unique_add_source(path) is True
    # second run is a no-op and reports it did nothing
    assert migrate_tags_unique_add_source(path) is False
    conn = sqlite3.connect(path)
    n = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
    conn.close()
    assert n == 1


def test_migration_preserves_autoincrement_high_water(tmp_path):
    """A new row after migration must get id > the prior max (no id reuse)."""
    path = str(tmp_path / "ai.db")
    _make_old_db(path)
    migrate_tags_unique_add_source(path)
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO tags (image_id, category, value, confidence, tag_source) "
        "VALUES (1, 'tags', 'standing', 0.7, 'wd_eva02')"
    )
    conn.commit()
    new_id = conn.execute("SELECT id FROM tags WHERE value='standing'").fetchone()[0]
    conn.close()
    assert new_id > 1


def test_migration_high_water_survives_deleted_max_row(tmp_path):
    """If the max-id row was deleted (seq > MAX(id)), the migration must keep the
    higher AUTOINCREMENT high-water — never reuse a freed id."""
    path = str(tmp_path / "hw.db")
    _make_old_db(path)  # inserts id=1
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO tags (image_id, category, value, confidence, tag_source) "
        "VALUES (1, 'tags', 'sitting', 0.7, 'wd_eva02')"
    )  # id=2
    conn.execute("DELETE FROM tags WHERE value='sitting'")  # MAX(id)=1, seq=2
    conn.commit()
    orig_seq = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name='tags'"
    ).fetchone()[0]
    conn.close()
    assert orig_seq == 2  # sanity

    migrate_tags_unique_add_source(path)

    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO tags (image_id, category, value, confidence, tag_source) "
        "VALUES (1, 'tags', 'kneeling', 0.7, 'wd_eva02')"
    )
    conn.commit()
    new_id = conn.execute("SELECT id FROM tags WHERE value='kneeling'").fetchone()[0]
    conn.close()
    assert new_id == 3, "freed id 2 was reused — high-water lowered by the migration"
