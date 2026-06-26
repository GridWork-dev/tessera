-- 005 — facets covering index (additive, idempotent). DRAFT — NOT YET APPLIED.
-- Apply only with explicit approval + a catalog.db backup:
--   cp data/catalog.db data/catalog.db.bak   (or scripts/backup_db.sh)
--   python -m pipeline.migrations --db data/catalog.db --file data/migrations/005_facets_covering_index.sql
--
-- Why: the new Browse UI computes disjunctive facet counts (result size per
-- candidate (category,value)) over the ~407k-row tags table. 004 added
-- (category,value); adding image_id makes the index COVERING for
-- `COUNT(DISTINCT image_id) ... GROUP BY category,value` — index-only scan, no
-- table lookup. Non-destructive: CREATE INDEX IF NOT EXISTS.

CREATE INDEX IF NOT EXISTS idx_tags_cat_val_img ON tags(category, value, image_id);

ANALYZE;
