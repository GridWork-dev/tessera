"""
Idempotent SQL migration runner for SQLite.

SQLite has no `ADD COLUMN IF NOT EXISTS`, so bare `ALTER TABLE ... ADD COLUMN`
statements fail on re-run. This runner reads a .sql file, splits it into
statements, and for ADD COLUMN statements guards against the live schema
(via PRAGMA table_info) before executing. All other statements (CREATE TABLE
IF NOT EXISTS, CREATE INDEX IF NOT EXISTS, etc.) are executed as-is.

Usage:
    python -m pipeline.migrations data/migrations/003_phase1_m5_schema.sql
    python -m pipeline.migrations --all
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

# Match: ALTER TABLE <name> ADD COLUMN <col> <type> [default ...]
_ADD_COLUMN_RE = re.compile(
    r"ALTER\s+TABLE\s+[\"'`\[]?(?P<table>\w+)[\"'`\]]?\s+ADD\s+COLUMN\s+"
    r"[\"'`\[]?(?P<col>\w+)[\"'`\]]?",
    re.IGNORECASE,
)

# Match: ALTER TABLE <name> DROP COLUMN <col>  (SQLite >= 3.35). Guarded the same
# way as ADD COLUMN — SQLite has no DROP COLUMN IF EXISTS, so a bare drop fails on
# re-run; skip it when the column is already gone (Wave 2c migration 016).
_DROP_COLUMN_RE = re.compile(
    r"ALTER\s+TABLE\s+[\"'`\[]?(?P<table>\w+)[\"'`\]]?\s+DROP\s+(?:COLUMN\s+)?"
    r"[\"'`\[]?(?P<col>\w+)[\"'`\]]?",
    re.IGNORECASE,
)


# A statement that reads the rating column FROM the images table (the 013
# backfill). Matched only to skip it once images.rating has been dropped.
_READS_IMAGES_RATING_RE = re.compile(
    r"FROM\s+images\b.*\brating\b", re.IGNORECASE | re.DOTALL
)


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _split_statements(sql: str) -> list[str]:
    """Split SQL into individual statements, stripping comments and blanks.

    Accumulates lines and ends a statement only when sqlite3.complete_statement
    says the buffer forms a complete SQL statement — it correctly accounts for
    quoting and trigger BEGIN..END bodies, so a naive ';'-at-end-of-line split
    can't mis-cut a TRIGGER body or a ';' inside a string literal.
    """
    statements: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        buf.append(line)
        candidate = "\n".join(buf)
        if sqlite3.complete_statement(candidate):
            statements.append(candidate.strip())
            buf = []
    if buf and (joined := "\n".join(buf).strip()):
        statements.append(joined)
    return statements


def apply_migration(conn: sqlite3.Connection, sql_path: Path) -> tuple[int, int]:
    """Apply one migration file. Returns (applied, skipped) statement counts."""
    sql = sql_path.read_text()
    applied = skipped = 0
    for stmt in _split_statements(sql):
        if not stmt:
            continue
        m = _ADD_COLUMN_RE.search(stmt)
        if m:
            table, col = m.group("table"), m.group("col")
            if col in _existing_columns(conn, table):
                print(f"  skip (exists): {table}.{col}")
                skipped += 1
                continue
        d = _DROP_COLUMN_RE.search(stmt)
        if d:
            table, col = d.group("table"), d.group("col")
            if col not in _existing_columns(conn, table):
                print(f"  skip (already dropped): {table}.{col}")
                skipped += 1
                continue
        # Historical backfill guard (Wave 2c): migration 013's
        #   INSERT ... SELECT ..., rating FROM images WHERE rating IS NOT NULL
        # reads images.rating to seed the Rating label set. That column was dropped
        # (016) and is gone from the ORM schema, so on a fresh DB the read references
        # a non-existent column. It is a one-time historical no-op there — skip it.
        if _READS_IMAGES_RATING_RE.search(stmt) and (
            "rating" not in _existing_columns(conn, "images")
        ):
            print("  skip (images.rating dropped): historical rating backfill")
            skipped += 1
            continue
        conn.execute(stmt)
        preview = " ".join(stmt.split())[:80]
        print(f"  apply: {preview}")
        applied += 1
    # One commit per FILE (not per statement) so a mid-file failure rolls the
    # whole file back instead of leaving it half-applied (audit P1).
    conn.commit()
    return applied, skipped


# ---------------------------------------------------------------------------
# A1 — add tag_source to the tags UNIQUE key (table rebuild; SQLite can't ALTER
# a UNIQUE constraint). User-approved schema change, 2026-06-23.
# ---------------------------------------------------------------------------
_TAGS_NEW_DDL = """
CREATE TABLE tags_new (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    category VARCHAR(32),
    value VARCHAR(256),
    confidence FLOAT,
    tag_source TEXT NOT NULL DEFAULT 'vlm',
    CONSTRAINT uq_tag_image_cat_val_source
        UNIQUE (image_id, category, value, tag_source),
    FOREIGN KEY(image_id) REFERENCES images (id)
)
"""


def tags_unique_has_source(conn: sqlite3.Connection) -> bool:
    """True if the `tags` UNIQUE constraint already covers tag_source."""
    for seq, name, unique, origin, partial in conn.execute(
        "PRAGMA index_list('tags')"
    ).fetchall():
        if unique and origin == "u":  # origin 'u' == created by a UNIQUE constraint
            cols = [
                r[2] for r in conn.execute(f"PRAGMA index_info('{name}')").fetchall()
            ]
            if "tag_source" in cols:
                return True
    return False


def migrate_tags_unique_add_source(db_path: str | Path) -> bool:
    """Rebuild `tags` so its UNIQUE key is (image_id, category, value, tag_source).

    Lets both WD-EVA02 and JoyTag rows for the same tag value coexist (the
    cross-model agreement signal). Idempotent: returns True if it migrated,
    False if the schema already had tag_source in the unique key. Does the
    standard create-new / copy / drop / rename rebuild in one transaction with
    foreign keys off, then restores the AUTOINCREMENT high-water mark.
    """
    conn = sqlite3.connect(str(db_path))
    conn.isolation_level = None  # take explicit transaction control
    try:
        if tags_unique_has_source(conn):
            return False
        conn.execute("PRAGMA busy_timeout=5000")
        # Capture the original AUTOINCREMENT high-water BEFORE the rebuild: if the
        # max-id row was deleted, sqlite_sequence.seq exceeds MAX(id) and must win
        # so a freed id is never reused.
        seq_row = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'tags'"
        ).fetchone()
        orig_seq = seq_row[0] if seq_row else 0
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN")
        conn.execute(_TAGS_NEW_DDL)
        conn.execute(
            "INSERT INTO tags_new "
            "(id, image_id, category, value, confidence, tag_source) "
            "SELECT id, image_id, category, value, confidence, "
            "COALESCE(tag_source, 'vlm') FROM tags"
        )
        conn.execute("DROP TABLE tags")
        conn.execute("ALTER TABLE tags_new RENAME TO tags")
        # Restore the high-water = max(original seq, current MAX(id)); never lower it.
        max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM tags").fetchone()[0]
        new_seq = max(orig_seq, max_id)
        # sqlite_sequence has NO unique index, so INSERT OR REPLACE would append a
        # duplicate row (and AUTOINCREMENT then reads the stale one). Delete every
        # tags/tags_new row, then insert exactly one authoritative entry.
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('tags', 'tags_new')")
        conn.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES ('tags', ?)", (new_seq,)
        )
        # FK check BEFORE COMMIT, so a violation's ROLLBACK actually reverts the
        # rebuild (foreign_key_check works regardless of the foreign_keys pragma).
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"FK violations after tags rebuild: {violations[:5]}")
        conn.execute("COMMIT")
        conn.execute("PRAGMA foreign_keys=ON")
        return True
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply SQLite migrations idempotently")
    parser.add_argument("migration", nargs="?", help="Path to a .sql file")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Apply all migrations in data/migrations/ in order",
    )
    parser.add_argument(
        "--rebuild-tags-unique",
        action="store_true",
        help="A1: rebuild the tags table so its UNIQUE key includes tag_source.",
    )
    parser.add_argument("--db", default="data/catalog.db", help="Database path")
    args = parser.parse_args()

    if args.rebuild_tags_unique:
        did = migrate_tags_unique_add_source(args.db)
        print(
            "tags UNIQUE rebuilt to include tag_source"
            if did
            else "tags UNIQUE already includes tag_source — no-op"
        )
        return 0

    if not args.migration and not args.all:
        parser.error("provide a migration path, --all, or --rebuild-tags-unique")

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        if args.all:
            files = sorted((Path("data/migrations")).glob("*.sql"))
        else:
            files = [Path(args.migration)]

        total_applied = total_skipped = 0
        for f in files:
            print(f"=== {f.name} ===")
            a, s = apply_migration(conn, f)
            total_applied += a
            total_skipped += s
        print(
            f"\nDone: {total_applied} applied, {total_skipped} skipped across {len(files)} file(s)."
        )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
