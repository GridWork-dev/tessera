-- 011 — deep video layer (additive). DRAFT — NOT YET APPLIED.
-- Lane C of the platform-evolution build (docs/superpowers/specs/2026-06-24-deep-video-design.md).
-- Apply only with explicit approval + a catalog.db backup (scripts/backup_db.sh).
--
-- Additive only: new tables + indexes keyed to video_scenes (migration 006).
-- Touches NOTHING existing. The per-scene keyframe runs through the SAME compute
-- seam dispatcher as images (embed/tag/caption/detect); these tables persist the
-- scene-level results. Tier-0 scene tags already have a home (scene_tags, mig 006)
-- so this migration does NOT re-create it — it adds captions, transcript, and the
-- face-crop hand-off seam, plus per-scene model-run provenance.

-- Per-scene free-text VLM captions (Tier-2). Model-keyed + run-keyed so a re-run
-- with a different captioner does not clobber prior output (mirrors `captions`).
CREATE TABLE IF NOT EXISTS scene_captions (
    id            INTEGER PRIMARY KEY,
    scene_id      INTEGER REFERENCES video_scenes(id),
    model         TEXT,
    caption       TEXT,
    run_id        INTEGER REFERENCES model_runs(id),  -- provenance (mig 007)
    created_at    TEXT,
    UNIQUE(scene_id, model)
);

-- Per-scene audio transcript segments (Whisper). One scene may have many cues;
-- each row is a (start,end,text) segment with the source model + language so the
-- transcript is searchable and re-runnable. `segment_index` orders cues within a
-- scene. The full-scene text is the ordered concat of its segments.
CREATE TABLE IF NOT EXISTS scene_transcripts (
    id            INTEGER PRIMARY KEY,
    scene_id      INTEGER REFERENCES video_scenes(id),
    segment_index INTEGER,
    start_time    REAL,                       -- seconds, absolute in the source video
    end_time      REAL,
    text          TEXT,
    language      TEXT,                        -- detected/forced language code
    model         TEXT,                        -- e.g. faster-whisper:base
    run_id        INTEGER REFERENCES model_runs(id),
    created_at    TEXT
);

-- Face-detect hand-off seam (Tier-3 DETECT on the scene keyframe). This lane
-- DETECTS + writes the crop; the faces lane (pipeline/faces/) CONSUMES these rows
-- later to embed + cluster. We intentionally store only bbox + a crop path here
-- (no embedding, no person link) so the two lanes share a contract without one
-- importing the other. `embedded` is the resume key the faces lane flips.
CREATE TABLE IF NOT EXISTS scene_faces (
    id            INTEGER PRIMARY KEY,
    scene_id      INTEGER REFERENCES video_scenes(id),
    face_index    INTEGER,                     -- 0..n-1 within the scene keyframe
    bbox          TEXT,                         -- JSON [x1,y1,x2,y2] in keyframe px
    score         REAL,                         -- detector confidence
    crop_path     TEXT,                         -- relative to content root (paths.py)
    detector      TEXT,                         -- e.g. apple_vision / yunet
    embedded      INTEGER DEFAULT 0,            -- 0 = pending, 1 = faces lane consumed
    created_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_scene_captions_scene    ON scene_captions(scene_id);
CREATE INDEX IF NOT EXISTS idx_scene_transcripts_scene ON scene_transcripts(scene_id);
CREATE INDEX IF NOT EXISTS idx_scene_faces_scene       ON scene_faces(scene_id);
CREATE INDEX IF NOT EXISTS idx_scene_faces_pending     ON scene_faces(embedded);

ANALYZE;
