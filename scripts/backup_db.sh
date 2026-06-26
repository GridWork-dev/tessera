#!/usr/bin/env bash
# WAL-safe, atomic backup of the source-of-truth catalog DB.
# Uses sqlite3 `.backup` (consistent even while the tag run is writing in WAL
# mode) — NOT `cp`, which can copy a torn WAL state (the likely cause of the
# 2026-06-23 02:26 corruption). Gzips + prunes to a rolling window.
#
# Usage: scripts/backup_db.sh [path/to/catalog.db]
# Cron/launchd-friendly: prints the destination, exits non-zero on failure.
set -euo pipefail

DB="${1:-data/catalog.db}"
OUT="data/backups"
KEEP="${BACKUP_KEEP:-14}"

[ -f "$DB" ] || { echo "backup_db: no DB at $DB" >&2; exit 1; }
mkdir -p "$OUT"

TS="$(date +%Y%m%d-%H%M%S)"
DEST="$OUT/catalog-$TS.db"

# Atomic WAL-safe snapshot, then integrity-gate before we trust it.
sqlite3 "$DB" ".backup '$DEST'"
if ! sqlite3 "$DEST" 'PRAGMA integrity_check;' | grep -q '^ok$'; then
  echo "backup_db: integrity_check FAILED for $DEST — keeping for inspection" >&2
  exit 2
fi
gzip -f "$DEST"

# Prune: keep the newest $KEEP gzipped snapshots.
ls -1t "$OUT"/catalog-*.db.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f

echo "backup_db: ok → $DEST.gz ($(du -h "$DEST.gz" | cut -f1))"
