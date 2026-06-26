-- 015 — poster_locked: protect a user's manual poster pick from auto re-selection.
-- Additive + idempotent.
ALTER TABLE videos ADD COLUMN poster_locked INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_videos_poster_locked ON videos(poster_locked);
