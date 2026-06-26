"""Tests for the robust SQLite migration runner (pipeline/migrations.py).

Covers the statement splitter (sqlite3.complete_statement accumulator) against
the cases the old line-ending heuristic mis-handled — trigger BEGIN..END bodies
and ';' inside string literals — plus the load-bearing ADD COLUMN idempotency
guard and a full apply of every real data/migrations/*.sql file.

All against TEMP sqlite DBs — never the real catalog.db.
"""

import re
import sqlite3
from pathlib import Path

from pipeline.database import Database
from pipeline.migrations import _split_statements, apply_migration

# This repo's data/migrations dir (relative to this test file, not the possibly
# mis-set settings.project_root), discovered + version-sorted the same way
# pipeline.bootstrap._migration_files does.
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "data" / "migrations"
_MIGRATION_NUM_RE = re.compile(r"^(\d+)_")


def _migration_files() -> list[tuple[int, Path]]:
    out: list[tuple[int, Path]] = []
    for f in _MIGRATIONS_DIR.glob("*.sql"):
        m = _MIGRATION_NUM_RE.match(f.name)
        if m:
            out.append((int(m.group(1)), f))
    return sorted(out, key=lambda t: t[0])


def test_create_trigger_body_not_mis_split(tmp_path):
    """A CREATE TRIGGER ... BEGIN <stmt>; <stmt>; END; body is ONE statement."""
    sql = """
CREATE TABLE a (n INTEGER);
CREATE TABLE b (id INTEGER);
CREATE TRIGGER bump AFTER INSERT ON b BEGIN
    UPDATE a SET n = n + 1;
    DELETE FROM a WHERE n < 0;
END;
"""
    stmts = _split_statements(sql)
    # exactly 3: two CREATE TABLEs + one whole trigger (body not split on inner ';')
    assert len(stmts) == 3
    assert stmts[2].startswith("CREATE TRIGGER bump")
    assert stmts[2].rstrip().endswith("END;")

    # And it actually applies as a single statement against a temp DB.
    path = tmp_path / "trig.sql"
    path.write_text(sql)
    conn = sqlite3.connect(str(tmp_path / "trig.db"))
    try:
        applied, skipped = apply_migration(conn, path)
        assert (applied, skipped) == (3, 0)
        triggers = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
        assert triggers == [("bump",)]
    finally:
        conn.close()


def test_semicolon_in_string_literal_not_mis_split(tmp_path):
    """A ';' inside a quoted string literal does not end the statement early."""
    sql = "CREATE TABLE t (v TEXT);\nINSERT INTO t (v) VALUES ('a;b;c');\n"
    stmts = _split_statements(sql)
    assert len(stmts) == 2
    assert stmts[1] == "INSERT INTO t (v) VALUES ('a;b;c');"

    path = tmp_path / "str.sql"
    path.write_text(sql)
    conn = sqlite3.connect(str(tmp_path / "str.db"))
    try:
        apply_migration(conn, path)
        assert conn.execute("SELECT v FROM t").fetchone()[0] == "a;b;c"
    finally:
        conn.close()


def test_add_column_idempotency(tmp_path):
    """ALTER TABLE ADD COLUMN applies once, then skips on a second apply."""
    base = (
        "CREATE TABLE IF NOT EXISTS x (id INTEGER);\nALTER TABLE x ADD COLUMN y TEXT;\n"
    )
    path = tmp_path / "addcol.sql"
    path.write_text(base)
    conn = sqlite3.connect(str(tmp_path / "addcol.db"))
    try:
        # First apply: CREATE TABLE (applied) + ADD COLUMN (applied).
        applied, skipped = apply_migration(conn, path)
        assert (applied, skipped) == (2, 0)
        assert "y" in {r[1] for r in conn.execute("PRAGMA table_info(x)")}
        # Second apply: CREATE TABLE IF NOT EXISTS still "applies" (no-op DDL),
        # ADD COLUMN is guarded and skipped.
        applied2, skipped2 = apply_migration(conn, path)
        assert (applied2, skipped2) == (1, 1)
    finally:
        conn.close()


def test_drop_column_idempotency(tmp_path):
    """ALTER TABLE DROP COLUMN drops once, then skips on a second apply (Wave 2c).

    SQLite has no DROP COLUMN IF EXISTS, so the runner must PRAGMA-guard it the
    same way it guards ADD COLUMN — drop only when the column is still present.
    """
    base = "CREATE TABLE IF NOT EXISTS x (id INTEGER, doomed TEXT);\n"
    drop = "ALTER TABLE x DROP COLUMN doomed;\n"
    base_path = tmp_path / "base.sql"
    base_path.write_text(base)
    drop_path = tmp_path / "drop.sql"
    drop_path.write_text(drop)
    conn = sqlite3.connect(str(tmp_path / "drop.db"))
    try:
        apply_migration(conn, base_path)
        assert "doomed" in {r[1] for r in conn.execute("PRAGMA table_info(x)")}
        # First drop: applied.
        applied, skipped = apply_migration(conn, drop_path)
        assert (applied, skipped) == (1, 0)
        assert "doomed" not in {r[1] for r in conn.execute("PRAGMA table_info(x)")}
        # Second drop: guarded + skipped (column already gone), no error.
        applied2, skipped2 = apply_migration(conn, drop_path)
        assert (applied2, skipped2) == (0, 1)
    finally:
        conn.close()


def _fresh_base_db(db_path):
    """Build a temp DB the same way the codebase does: ORM tables (incl. videos,
    captions, users, owner_id columns) + the raw-SQL 002 tables that later
    migrations ALTER."""
    Database(str(db_path))  # creates all ORM tables
    conn = sqlite3.connect(str(db_path))
    try:
        mig002 = next(p for v, p in _migration_files() if v == 2)
        conn.executescript(mig002.read_text())
        conn.commit()
    finally:
        conn.close()


def test_all_real_migrations_apply_and_are_idempotent(tmp_path):
    """Every real data/migrations/*.sql applies cleanly to a fresh temp DB in
    version order, and re-applying is idempotent (no error; ADD COLUMNs skip)."""
    migrations = _migration_files()
    assert migrations, "no migration files discovered"

    db_path = tmp_path / "catalog.db"
    _fresh_base_db(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        # First pass: apply every migration (002 already in base; re-applying is
        # safe — its CREATE TABLE IF NOT EXISTS are no-ops).
        for _version, path in migrations:
            apply_migration(conn, path)

        # Second pass: idempotent — must not raise, and every ADD COLUMN must be
        # skipped (already present), so no migration nets new ADD COLUMNs.
        for _version, path in migrations:
            applied, skipped = apply_migration(conn, path)
            # Any ALTER ... ADD COLUMN in the file must have been skipped now.
            text = path.read_text().lower()
            if "add column" in text:
                assert skipped > 0, f"{path.name}: expected skipped ADD COLUMNs"
    finally:
        conn.close()


def test_split_statements_drops_full_line_comments():
    sql = "-- a comment\nCREATE TABLE t (id INTEGER);\n-- trailing\n"
    stmts = _split_statements(sql)
    assert stmts == ["CREATE TABLE t (id INTEGER);"]
