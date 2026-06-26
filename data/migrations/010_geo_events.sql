-- 010 — geo/places + events schema (additive). DRAFT — NOT YET APPLIED.
-- Lane B of the platform-evolution build (docs/superpowers/specs/2026-06-24-geo-events-design.md).
-- Apply only with explicit approval + a catalog.db backup (scripts/backup_db.sh).
-- Additive only: new tables + indexes + nullable ADD COLUMNs on images/videos.
-- Touches nothing existing. GPS comes from each file's own EXIF (ExifTool);
-- place names are resolved offline (reverse_geocoder / GeoNames); events are the
-- self-written time-gap + GPS-DBSCAN clusterer's output. Keep in sync with
-- pipeline/geo/.

-- A distinct geographic place (de-duped by place_key, a rounded lat/lon grid).
CREATE TABLE IF NOT EXISTS places (
    id            INTEGER PRIMARY KEY,
    place_key     TEXT UNIQUE,                 -- rounded "lat,lon" grid key (dedupe)
    name          TEXT,                        -- nearest GeoNames place name
    admin1        TEXT,                        -- state / region
    admin2        TEXT,                        -- county / district
    cc            TEXT,                        -- ISO country code
    lat           REAL,
    lon           REAL,
    created_at    TEXT
);

-- An auto-album / trip: a time-gap + GPS-DBSCAN cluster of items.
CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY,
    start_time    TEXT,                        -- earliest member timestamp
    end_time      TEXT,                        -- latest member timestamp
    centroid_lat  REAL,                        -- mean GPS of members (nullable)
    centroid_lon  REAL,
    member_count  INTEGER DEFAULT 0,
    label         TEXT,                        -- optional human/auto title
    created_at    TEXT
);

-- Event membership. owner_type mirrors vec_owner so one event spans images and
-- videos without overloading images.id.
CREATE TABLE IF NOT EXISTS event_members (
    event_id      INTEGER REFERENCES events(id),
    owner_type    TEXT CHECK(owner_type IN ('image','video')),
    owner_id      INTEGER,
    PRIMARY KEY (event_id, owner_type, owner_id)
);

-- Additive GPS / place / event columns on the existing media tables.
ALTER TABLE images ADD COLUMN gps_lat  REAL;
ALTER TABLE images ADD COLUMN gps_lon  REAL;
ALTER TABLE images ADD COLUMN place_id INTEGER REFERENCES places(id);
ALTER TABLE images ADD COLUMN event_id INTEGER REFERENCES events(id);

ALTER TABLE videos ADD COLUMN gps_lat  REAL;
ALTER TABLE videos ADD COLUMN gps_lon  REAL;
ALTER TABLE videos ADD COLUMN place_id INTEGER REFERENCES places(id);
ALTER TABLE videos ADD COLUMN event_id INTEGER REFERENCES events(id);

CREATE INDEX IF NOT EXISTS idx_places_key        ON places(place_key);
CREATE INDEX IF NOT EXISTS idx_event_members_evt ON event_members(event_id);
CREATE INDEX IF NOT EXISTS idx_event_members_own ON event_members(owner_type, owner_id);
CREATE INDEX IF NOT EXISTS idx_images_place      ON images(place_id);
CREATE INDEX IF NOT EXISTS idx_images_event      ON images(event_id);
CREATE INDEX IF NOT EXISTS idx_videos_place      ON videos(place_id);
CREATE INDEX IF NOT EXISTS idx_videos_event      ON videos(event_id);

ANALYZE;
