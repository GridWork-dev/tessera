-- 008 — caption FTS5 (additive). APPROVED 2026-06-23 (+ backup).
-- Standalone (NOT external-content) FTS5 over captions.caption so the caption
-- keyword lane + RRF fusion in webui/search.py (CAPTION_FTS_TABLE / _caption_fts)
-- activate automatically when the full Tier-2 caption run lands.
--
-- Standalone (stores a copy of the text) is chosen over external-content + sync
-- triggers because the caption writers (import_h100_artifacts.py:209,
-- tier2_captioner.py) use raw INSERT OR IGNORE that bypass SQLAlchemy events —
-- so we REBUILD the index after each import (pipeline/database.py::
-- rebuild_caption_fts), per roadmap GATE 4, rather than rely on triggers that a
-- raw INSERT would never fire. rowid == captions.id so a rebuild is a clean
-- DELETE + INSERT...SELECT. Population is owned by rebuild_caption_fts(), NOT this
-- migration, so re-applying the migration is a pure no-op (no duplicate rows).

CREATE VIRTUAL TABLE IF NOT EXISTS captions_fts USING fts5(
    caption,
    image_id UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
