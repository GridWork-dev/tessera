"""Auto-migrate-with-backup boot hook + admin seeding (Spec C, P0.3 + §6).

Highest-risk change in the productionization plan — it touches the user's
irreplaceable library — so the contract is strict and non-negotiable:

  1. **Backup first.** A WAL-safe ``scripts/backup_db.sh`` snapshot runs BEFORE
     any migration. If the backup fails, we do NOT migrate.
  2. **Version ledger.** SQLite ``PRAGMA user_version`` records the highest
     migration applied. Upgrades are detectable; **downgrades are refused**
     (a DB stamped newer than the code's known max means "do not start").
  3. **Fail-closed.** Any error in backup or migration raises — the caller
     (the web server boot) refuses to serve rather than half-migrate.
  4. **Opt-in for the real DB.** Migrations only run on boot when explicitly
     enabled (``MEDIA_PIPELINE_AUTO_MIGRATE=1``), so importing ``webui.main`` in
     the test suite never mutates anything. The function is also directly
     callable with an explicit path for tests against a TEMP db.

The migration runner (``pipeline.migrations.apply_migration``) is already
idempotent; this module adds the boot hook, the version ledger, the backup gate,
and the fail-closed wrapper around it.
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

from pipeline import auth, migrations
from pipeline.database import Database
from pipeline.settings import settings

# Migration filenames are NNN_*.sql; the numeric prefix is the schema version
# the file brings the DB to. The user_version ledger stores the max applied.
_MIGRATION_NUM_RE = re.compile(r"^(\d+)_")


def _migrations_dir() -> Path:
    return settings.project_root / "data" / "migrations"


def _migration_files() -> list[tuple[int, Path]]:
    """All migration files as (version, path), sorted ascending by version."""
    out: list[tuple[int, Path]] = []
    for f in _migrations_dir().glob("*.sql"):
        m = _MIGRATION_NUM_RE.match(f.name)
        if m:
            out.append((int(m.group(1)), f))
    return sorted(out, key=lambda t: t[0])


def _get_user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    # PRAGMA user_version does not accept a bound parameter.
    conn.execute(f"PRAGMA user_version = {int(version)}")
    conn.commit()


def backup_db(db_path: Path) -> Path:
    """Run the WAL-safe backup script; return the snapshot path it printed.

    Raises if the script is missing or exits non-zero (fail-closed).
    """
    script = settings.project_root / "scripts" / "backup_db.sh"
    if not script.is_file():
        raise RuntimeError(f"backup script not found: {script}")
    proc = subprocess.run(
        ["bash", str(script), str(db_path)],
        capture_output=True,
        text=True,
        cwd=str(settings.project_root),
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"pre-migration backup FAILED (rc={proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return Path(proc.stdout.strip().split("→")[-1].strip().split(" ")[0])


def seed_admin(db_path: Path) -> None:
    """Create/refresh the admin user from MEDIA_PIPELINE_ADMIN_PASSWORD.

    No-op when no admin password is configured. Idempotent: updates the existing
    admin's hash in place rather than creating duplicates. Requires the ``users``
    table (migration 012) to exist; callers run this after migrations.
    """
    pw = auth.admin_password()
    if not pw:
        return
    username = auth.admin_username()
    pw_hash = auth.hash_password(pw)
    conn = sqlite3.connect(str(db_path))
    try:
        has_users = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if not has_users:
            raise RuntimeError("users table missing — run migration 012 first")
        row = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET password_hash = ?, role = 'admin', is_active = 1 "
                "WHERE id = ?",
                (pw_hash, row[0]),
            )
        else:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, is_active) "
                "VALUES (?, ?, 'admin', 1)",
                (username, pw_hash),
            )
        conn.commit()
    finally:
        conn.close()


def run_pending_migrations(db_path: str | Path, *, do_backup: bool = True) -> int:
    """Apply pending migrations with the full safety contract; return new version.

    Steps: read ``user_version`` ledger → refuse downgrade → backup → apply each
    pending file in order → stamp the new version. Fail-closed: any exception
    propagates and no version is stamped past the last fully-applied file.
    """
    db_path = Path(db_path)
    files = _migration_files()
    if not files:
        return 0
    max_known = files[-1][0]

    # Ensure the DB + base ORM schema exist (idempotent) before stamping/migrating.
    Database(str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        current = _get_user_version(conn)
        if current > max_known:
            raise RuntimeError(
                f"DB schema version {current} is NEWER than this build's max "
                f"{max_known} — refusing to start (downgrade not supported)."
            )
        pending = [(v, f) for (v, f) in files if v > current]
        if not pending:
            return current
    finally:
        conn.close()

    if do_backup:
        backup_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        new_version = _get_user_version(conn)
        for version, f in pending:
            migrations.apply_migration(conn, f)  # commits the file's statements
            new_version = version
            _set_user_version(conn, new_version)
            conn.commit()  # stamp the version durably alongside the file
        return new_version
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_persisted_auth_env() -> None:
    """Export the wizard-persisted ``auth`` block into the MEDIA_PIPELINE_* env the
    auth layer reads, so a wizard-configured install actually enforces auth on the
    next boot (audit P1 — the block was written but never consumed).

    Uses ``setdefault`` so an explicit env var always wins (e.g. a serve.local.env
    ``MEDIA_PIPELINE_AUTH_ENABLED=0`` override). No-op when there is no auth block.
    """
    try:
        import yaml

        from pipeline.settings import _user_config_path

        cfg_path = _user_config_path()
        if not cfg_path.exists():
            return
        block = (yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}).get("auth")
    except Exception:  # noqa: BLE001 — never let config parsing break boot
        return
    if not block or not block.get("enabled"):
        return
    os.environ.setdefault("MEDIA_PIPELINE_AUTH_ENABLED", "1")
    if block.get("admin_username"):
        os.environ.setdefault(
            "MEDIA_PIPELINE_ADMIN_USERNAME", str(block["admin_username"])
        )
    if block.get("secret"):
        os.environ.setdefault("MEDIA_PIPELINE_AUTH_SECRET", str(block["secret"]))


def boot() -> None:
    """Web-server boot hook: apply persisted auth env, auto-migrate (guarded), seed.

    Migrations run against the configured DB ONLY when ``MEDIA_PIPELINE_AUTO_MIGRATE``
    is truthy — so importing ``webui.main`` in tests never mutates a DB. The
    auth-env export runs unconditionally (it only reads config + sets env via
    setdefault). Fail-closed on any migration error.
    """
    apply_persisted_auth_env()
    enabled = os.environ.get("MEDIA_PIPELINE_AUTO_MIGRATE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if not enabled:
        return
    db_path = settings.database_path
    run_pending_migrations(db_path)
    seed_admin(db_path)


if __name__ == "__main__":  # manual: python -m pipeline.bootstrap [db_path]
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else settings.database_path
    v = run_pending_migrations(target)
    seed_admin(target)
    print(f"bootstrap: schema at user_version={v} for {target}")
