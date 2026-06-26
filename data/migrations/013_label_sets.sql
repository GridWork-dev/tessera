-- 013 — user-defined label sets (facets). Generalizes the fixed images.rating
-- enum into removable single/multi-select label groups. See
-- docs/superpowers/specs/2026-06-25-platform-customization-overhaul-design.md (3.2).
-- Additive + idempotent under pipeline.migrations.apply_migration:
--   CREATE ... IF NOT EXISTS self-guards; ADD COLUMN is PRAGMA-guarded;
--   INSERT OR IGNORE + the unique index make the seed + backfill re-runnable.
-- Single-select ("<=1 value per set per image") is enforced in the application
-- layer (pipeline/labels/store.py) — SQLite partial-index predicates cannot
-- contain subqueries. images.rating is RETAINED here; migration 014 drops it.
-- Apply ONLY via the auto-migrate-with-backup boot hook, or manually AFTER:
--     bash scripts/backup_db.sh
--     python -m pipeline.migrations data/migrations/013_label_sets.sql --db data/catalog.db

CREATE TABLE IF NOT EXISTS label_sets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL UNIQUE,
    single_select INTEGER NOT NULL DEFAULT 0,
    color         TEXT,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    is_system     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS label_definitions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    set_id      INTEGER NOT NULL REFERENCES label_sets(id) ON DELETE CASCADE,
    value       TEXT    NOT NULL,
    color       TEXT,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(set_id, value)
);

ALTER TABLE user_labels ADD COLUMN set_id INTEGER REFERENCES label_sets(id);

CREATE INDEX IF NOT EXISTS idx_user_labels_set ON user_labels(set_id, value);
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_labels_set_val
    ON user_labels(image_id, set_id, value);

INSERT OR IGNORE INTO label_sets (id, name, single_select, is_system, sort_order)
VALUES (1, 'Rating', 1, 1, 0);

INSERT OR IGNORE INTO label_definitions (set_id, value, color, sort_order) VALUES
    (1, 'unrated',    '#717c8c', 0),
    (1, 'sfw',        '#5ead84', 1),
    (1, 'suggestive', '#cba85a', 2),
    (1, 'nsfw',       '#d27a7a', 3);

-- Backfill the Rating set from images.rating. Adopt any pre-existing legacy
-- rating rows (set_id IS NULL) into set 1 FIRST, otherwise the INSERT OR IGNORE
-- below collides with the inherited table-level UNIQUE(image_id, category, value)
-- from migration 002 and silently drops those images from the new model.
UPDATE user_labels
SET set_id = 1
WHERE set_id IS NULL AND category = 'rating';

INSERT OR IGNORE INTO user_labels (image_id, set_id, category, value, owner_id)
SELECT id, 1, 'rating', rating, 1
FROM images
WHERE rating IS NOT NULL AND rating <> 'unrated';
