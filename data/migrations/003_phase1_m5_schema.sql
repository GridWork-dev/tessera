-- 003_phase1_m5_schema.sql
-- Phase 1 — M5 tiered-architecture schema additions.
-- Source: docs/decisions/0001-m5-tiered-architecture.md, docs/kickoff-phase-1-2.md §1a.
--
-- Idempotency note: SQLite has no `ADD COLUMN IF NOT EXISTS`. The Python apply
-- step (see pipeline/migrations.py::apply_phase1_m5) guards each ALTER against
-- PRAGMA table_info. CREATE TABLE IF NOT EXISTS is natively safe to re-run.
-- `tags.confidence` was added in a prior partial run and is intentionally not
-- re-added here.

-- tags: provenance (which tier/model produced this tag) + explicit confidence.
ALTER TABLE tags ADD COLUMN tag_source TEXT DEFAULT 'vlm';
    -- joytag | wd_eva02 | vlm | openrouter | user

-- images: NudeNet output (Tier 3). Metadata only — NEVER used as a gate.
ALTER TABLE images ADD COLUMN nudenet_regions TEXT;
    -- JSON array of {"label": str, "score": float, "box": [x1,y1,x2,y2]}
ALTER TABLE images ADD COLUMN nudenet_checked INTEGER DEFAULT 0;

-- captions (Tier 2 — JoyCaption PyTorch bf16 dedicated). Built now so the
-- schema is complete; populated in Phase 3.
CREATE TABLE IF NOT EXISTS captions (
    id INTEGER PRIMARY KEY,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    model TEXT,
    caption TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(image_id, model)
);

CREATE INDEX IF NOT EXISTS idx_captions_image ON captions(image_id);
