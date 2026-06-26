-- 009 — faces / people schema (additive). DRAFT — NOT YET APPLIED.
-- Lane A (faces) of the platform-evolution build. See
-- docs/superpowers/specs/2026-06-24-faces-design.md.
-- Apply ONLY with explicit approval + a catalog.db backup (scripts/backup_db.sh):
--     bash scripts/backup_db.sh
--     sqlite3 data/catalog.db < data/migrations/009_faces.sql
-- Additive only: two new tables + indexes; touches nothing existing. References
-- images(id), which already exists.
--
-- PRIVACY: face vectors are GDPR Art.9 / BIPA biometric data. The feature is
-- off-by-default (config flag faces.enabled) and every person is fully erasable
-- (DELETE /api/faces/people/{id} removes the person AND their face vectors).

CREATE TABLE IF NOT EXISTS people (
    id            INTEGER PRIMARY KEY,
    name          TEXT,                          -- nullable: unnamed cluster until labeled
    cover_face_id INTEGER,                        -- representative face (UI thumbnail)
    face_count    INTEGER DEFAULT 0,             -- maintained on mutation
    created_at    TEXT,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS faces (
    id             INTEGER PRIMARY KEY,
    image_id       INTEGER REFERENCES images(id),
    person_id      INTEGER REFERENCES people(id), -- NULL = unclustered/unassigned
    bbox           TEXT,                          -- json [x,y,w,h], normalized 0..1, top-left origin
    embedding_blob BLOB,                          -- float32 little-endian, embedding_dim values
    embedding_dim  INTEGER,                        -- 128 (SFace) | 512 (ArcFace)
    detector       TEXT,                          -- e.g. apple_vision
    embedder       TEXT,                          -- sface | arcface (partitions comparisons)
    confidence     REAL,
    created_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_faces_image    ON faces(image_id);
CREATE INDEX IF NOT EXISTS idx_faces_person   ON faces(person_id);
CREATE INDEX IF NOT EXISTS idx_faces_embedder ON faces(embedder);
CREATE INDEX IF NOT EXISTS idx_people_name    ON people(name);

ANALYZE;
