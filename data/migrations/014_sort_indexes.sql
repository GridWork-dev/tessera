-- 014 — covering indexes for the new sort options (date/name/size + video duration).
-- Additive + idempotent. See docs/superpowers/specs/2026-06-25-platform-customization-overhaul-design.md.
CREATE INDEX IF NOT EXISTS idx_images_created_at  ON images(created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_images_modified_at ON images(modified_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_images_filename    ON images(filename ASC, id ASC);
CREATE INDEX IF NOT EXISTS idx_images_filesize    ON images(filesize DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_videos_filename    ON videos(filename ASC, id ASC);
CREATE INDEX IF NOT EXISTS idx_videos_filesize    ON videos(filesize DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_videos_duration    ON videos(duration DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_videos_imported_at ON videos(imported_at DESC, id DESC);
