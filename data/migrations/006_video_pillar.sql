-- 006 — video pillar schema (additive). DRAFT — NOT YET APPLIED.
-- Per docs/roadmap-platform-2026.md Pillar C + outputs/research/02-video-pipeline.md.
-- Apply only with explicit approval + a catalog.db backup (scripts/backup_db.sh).
-- Additive only: new tables + indexes; touches nothing existing. Reuses the
-- existing SigLIP→TurboVec stack for scene keyframes via the vec_owner map (so
-- one ANN index serves images AND video scenes without overloading images.id).

CREATE TABLE IF NOT EXISTS videos (
    id            INTEGER PRIMARY KEY,
    path          TEXT,                       -- relative to content root (resolve via paths.py)
    filename      TEXT,
    directory     TEXT,
    person        TEXT,
    file_hash     TEXT UNIQUE,
    duration      REAL,                       -- seconds (ffprobe)
    width         INTEGER,
    height        INTEGER,
    fps           REAL,
    codec         TEXT,
    bitrate       INTEGER,
    has_audio     INTEGER DEFAULT 0,
    filesize      INTEGER,
    poster_path   TEXT,                       -- representative frame (skip black/title)
    contact_sheet_path TEXT,                  -- NxN storyboard
    sprite_path   TEXT,                       -- scrub sprite mosaic
    vtt_path      TEXT,                       -- WebVTT cue map for scrub previews
    rating        TEXT DEFAULT 'unrated',     -- unrated|sfw|suggestive|nsfw
    media_type    TEXT DEFAULT 'video',
    processed     INTEGER DEFAULT 0,          -- 0=not enriched, 1=done (resume key)
    created_at    TEXT,
    imported_at   TEXT
);

CREATE TABLE IF NOT EXISTS video_scenes (
    id            INTEGER PRIMARY KEY,
    video_id      INTEGER REFERENCES videos(id),
    scene_index   INTEGER,
    start_time    REAL,                       -- seconds (PySceneDetect)
    end_time      REAL,
    keyframe_path TEXT,                       -- representative frame for this scene
    caption       TEXT,                       -- Tier-2 caption (optional)
    processed     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scene_tags (
    id            INTEGER PRIMARY KEY,
    scene_id      INTEGER REFERENCES video_scenes(id),
    category      TEXT,
    value         TEXT,
    confidence    REAL,
    tag_source    TEXT
);

-- Unify the vector index across pillars: one ANN/vec rowid → its owner.
CREATE TABLE IF NOT EXISTS vec_owner (
    vec_id        INTEGER PRIMARY KEY,        -- rowid in the vec/ANN store
    owner_type    TEXT CHECK(owner_type IN ('image','scene')),
    owner_id      INTEGER                     -- images.id or video_scenes.id
);

CREATE INDEX IF NOT EXISTS idx_video_scenes_video ON video_scenes(video_id);
CREATE INDEX IF NOT EXISTS idx_scene_tags_scene   ON scene_tags(scene_id);
CREATE INDEX IF NOT EXISTS idx_scene_tags_cat_val ON scene_tags(category, value);
CREATE INDEX IF NOT EXISTS idx_videos_processed   ON videos(processed);
CREATE INDEX IF NOT EXISTS idx_vec_owner_owner    ON vec_owner(owner_type, owner_id);

ANALYZE;
