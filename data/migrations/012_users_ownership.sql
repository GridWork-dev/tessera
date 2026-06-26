-- 012 — users + ownership (multi-user, designed up front). Spec B + §6.
-- See docs/superpowers/specs/2026-06-24-productionization-design.md §6.
-- Additive ONLY: one new table + nullable owner_id columns + a backfill.
-- Apply ONLY via the auto-migrate-with-backup boot hook (pipeline.bootstrap)
-- or, for a manual run, AFTER a catalog.db backup:
--     bash scripts/backup_db.sh
--     sqlite3 data/catalog.db < data/migrations/012_users_ownership.sql
-- Idempotent under pipeline.migrations.apply_migration: the ADD COLUMN lines
-- are guarded by PRAGMA table_info; CREATE ... IF NOT EXISTS is self-guarding;
-- the backfill UPDATEs only NULL rows and the system-user INSERT is OR IGNORE.
--
-- Ownership model: a nullable owner_id on the user-data tables. NULL means
-- "legacy / unassigned" and resolves to the sole admin in single-user installs,
-- so every existing query is unaffected until multi-user is enabled. Model-output
-- tables (tags, captions, embeddings, video_scenes, model_runs) inherit ownership
-- transitively through their parent FK and get no column of their own.

-- The users table. First registered user becomes admin (Immich pattern); the
-- first-run wizard (§7) creates that row. id=1 is reserved for the system/default
-- user that owns all pre-multi-user rows.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',          -- 'admin' | 'user'
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Reserve id=1 as the system/default owner of all existing single-user data.
-- A blank password_hash means "cannot log in as this account" — the first-run
-- wizard creates a real admin separately. OR IGNORE keeps the migration
-- idempotent and never clobbers a real admin that already took id=1.
INSERT OR IGNORE INTO users (id, username, password_hash, role, is_active)
VALUES (1, 'system', '', 'admin', 1);

-- Nullable ownership columns on every user-data table (§6).
ALTER TABLE images ADD COLUMN owner_id INTEGER REFERENCES users(id);
ALTER TABLE videos ADD COLUMN owner_id INTEGER REFERENCES users(id);
ALTER TABLE collections ADD COLUMN owner_id INTEGER REFERENCES users(id);
ALTER TABLE notes ADD COLUMN owner_id INTEGER REFERENCES users(id);
ALTER TABLE grids ADD COLUMN owner_id INTEGER REFERENCES users(id);
ALTER TABLE exclusion_rules ADD COLUMN owner_id INTEGER REFERENCES users(id);
ALTER TABLE user_labels ADD COLUMN owner_id INTEGER REFERENCES users(id);

-- Backfill existing rows to the system user (id=1) in one pass. Each UPDATE
-- touches only rows still NULL, so re-running is a no-op.
UPDATE images          SET owner_id = 1 WHERE owner_id IS NULL;
UPDATE videos          SET owner_id = 1 WHERE owner_id IS NULL;
UPDATE collections     SET owner_id = 1 WHERE owner_id IS NULL;
UPDATE notes           SET owner_id = 1 WHERE owner_id IS NULL;
UPDATE grids           SET owner_id = 1 WHERE owner_id IS NULL;
UPDATE exclusion_rules SET owner_id = 1 WHERE owner_id IS NULL;
UPDATE user_labels     SET owner_id = 1 WHERE owner_id IS NULL;

-- Indexes for the owner-scoped list/filter queries multi-user adds.
CREATE INDEX IF NOT EXISTS idx_images_owner ON images(owner_id);
CREATE INDEX IF NOT EXISTS idx_videos_owner ON videos(owner_id);
CREATE INDEX IF NOT EXISTS idx_collections_owner ON collections(owner_id);
