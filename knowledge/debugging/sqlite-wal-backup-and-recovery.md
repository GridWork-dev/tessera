# SQLite WAL: backup & corruption recovery

**Incident (2026-06-23 02:26):** `data/catalog.db` corrupted; `catalog.db.corrupt-*`
left in `data/`. Cause: concurrent writers + copying a live WAL database with `cp`
(captures a torn WAL/SHM state). Recovered from a good backup.

## Rules
- **Never `cp` a live WAL DB.** Use `sqlite3 DB '.backup dest'` — atomic, consistent
  even while the tag run writes. `scripts/backup_db.sh` does this + an
  `PRAGMA integrity_check` gate + gzip + rolling prune. Loaded as a launchd daily job
  (`com.mediapipeline.dbbackup`, 03:30).
- **Concurrency pragmas** (`database.py::apply_sqlite_pragmas`): `WAL`,
  `busy_timeout=5000`, `synchronous=NORMAL` — enable a safe concurrent reader
  (backend) + writer (tag run). Set BEFORE `create_all` and on every raw connection.
- Backups live in `data/backups/` (gitignored). Restore: `gunzip -c <snap>.db.gz > catalog.db`
  (stop writers first), then `PRAGMA integrity_check`.
