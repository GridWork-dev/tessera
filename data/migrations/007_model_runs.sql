-- 007 — model_runs provenance (additive). APPROVED 2026-06-23 (+ backup).
-- Persists the run-level manifest the H100 batch box emits (run_manifest.json),
-- which scripts/import_h100_artifacts.py currently discards (roadmap E6). Adds a
-- nullable run_id FK on tags/captions/embeddings so every imported row is
-- traceable to the run that produced it — the base every Track 3-4 import writes
-- into. Additive only: one new table + three nullable ADD COLUMNs + indexes.
-- Keep in sync with pipeline/database.py (ModelRun + Tag/Caption/Embedding.run_id).

CREATE TABLE IF NOT EXISTS model_runs (
    id            INTEGER PRIMARY KEY,
    run_key       TEXT UNIQUE,                 -- manifest run id (stable natural key)
    tier          TEXT,                        -- tier0 | tier1 | tier2 | tier3
    model_id      TEXT,                        -- HF model id (e.g. google/siglip-so400m-patch14-384)
    revision      TEXT,                        -- model revision / commit pin
    precision     TEXT,                        -- fp16 | fp32
    host          TEXT,                        -- where it ran (vast-h100 | local)
    git_sha       TEXT,                        -- code revision on the box
    item_count    INTEGER,                     -- rows the run produced
    started_at    TEXT,
    finished_at   TEXT,
    status        TEXT DEFAULT 'complete',
    manifest_json TEXT,                        -- full raw run_manifest.json
    created_at    TEXT
);

ALTER TABLE tags ADD COLUMN run_id INTEGER REFERENCES model_runs(id);
ALTER TABLE captions ADD COLUMN run_id INTEGER REFERENCES model_runs(id);
ALTER TABLE embeddings ADD COLUMN run_id INTEGER REFERENCES model_runs(id);

CREATE INDEX IF NOT EXISTS idx_tags_run     ON tags(run_id);
CREATE INDEX IF NOT EXISTS idx_captions_run ON captions(run_id);
CREATE INDEX IF NOT EXISTS idx_model_runs_key ON model_runs(run_key);

ANALYZE;
