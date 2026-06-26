# Pattern: resumable, crash-safe batch processing

Used by the corpus tag/embed runs so a kill -9 never loses or double-does work.

- **Resume key**: `images.processed` (0 = not done). Select with
  `WHERE processed=0 ORDER BY id` — deterministic, restart-safe.
- **Per-image transaction**: clear → tag → finalize, committing per image. A crash
  loses at most the in-flight image; everything prior is durable.
- **Finalize gate**: only set `processed=1` when all required tiers for that image
  succeeded; roll back on tier failure (don't mark partial work done).
- **Index checkpointing** (Tier 1): `embed_unprocessed(..., checkpoint_every=N)` saves
  the TurboVec `.idx` + commits the vec table every N — partial progress survives a crash.
- Refs: `pipeline/tag_runner.py`, `pipeline/tier1_embedder.py::embed_unprocessed`,
  `tests/test_tier1_checkpoint.py`.
