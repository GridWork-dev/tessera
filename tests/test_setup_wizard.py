"""Tests for the first-run setup wizard endpoints (Spec F / §7 P0.4).

Fully isolated: a minimal FastAPI app wiring ONLY ``webui.routes_setup.router``
against a TEMP per-user config + TEMP db. No network (weights pull is mocked /
apply-gated off), no real ``data/catalog.db`` (the apply gate stays OFF), no
``config.yaml`` write (the wizard targets ``MEDIA_PIPELINE_SETUP_CONFIG``).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pipeline.compute import detect
from pipeline.database import Database
from pipeline.settings import REPO_ROOT, reload_settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A wizard client over a temp config + temp db, apply-gate OFF (safe)."""
    user_cfg = tmp_path / "user_config.yaml"
    db = tmp_path / "catalog.db"
    Database(str(db))  # base schema on a temp file (never the real catalog)

    monkeypatch.setenv("MEDIA_PIPELINE_PROJECT_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("MEDIA_PIPELINE_DATABASE_PATH", str(db))
    # Redirect BOTH the wizard write and the settings per-user-config read to a
    # temp file (never the real ~/.../media-pipeline/config.yaml or config.yaml).
    import pipeline.settings as settings_mod

    monkeypatch.setattr(settings_mod, "_user_config_path", lambda: user_cfg)
    # Simulate a FRESH install: neutralize the repo's skip-worktree config.yaml
    # (in this worktree it carries the maintainer's absolute paths and, being the
    # highest-precedence YAML layer, would otherwise clobber the wizard's writes).
    monkeypatch.setattr(settings_mod, "REPO_CONFIG_YAML", tmp_path / "no-config.yaml")
    # Apply gate explicitly OFF: no network pulls, no DB seed.
    monkeypatch.delenv("MEDIA_PIPELINE_SETUP_APPLY", raising=False)
    # Keep weights probing pointed at an empty temp models dir (everything absent).
    monkeypatch.setenv("MEDIA_PIPELINE_MODELS_CACHE_DIR", str(tmp_path / "models"))
    reload_settings()

    from webui.routes_setup import router as setup_router

    app = FastAPI()
    app.include_router(setup_router)
    try:
        yield TestClient(app), user_cfg, db
    finally:
        reload_settings()


def _add_users_table(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    conn.executescript(
        "CREATE TABLE IF NOT EXISTS users ("
        " id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT,"
        " role TEXT, is_active INTEGER DEFAULT 1)"
    )
    conn.commit()
    conn.close()


# --- status / first-run gate --------------------------------------------------


def test_status_first_run_needed_on_empty(client):
    c, _cfg, _db = client
    r = c.get("/api/setup/status")
    assert r.status_code == 200, r.text
    body = r.json()
    # Empty config + no admin + missing weights => wizard must show.
    assert body["first_run_needed"] is True
    assert body["apply_enabled"] is False
    assert body["steps"]["library"]["configured"] is False
    assert body["steps"]["auth"]["admin_exists"] is False
    assert body["steps"]["weights"]["offline_ready"] is False
    # Compute step always reports a concrete detected backend.
    assert body["steps"]["compute"]["detected_backend"] in {
        detect.BACKEND_MPS,
        detect.BACKEND_CUDA,
        detect.BACKEND_DIRECTML,
        detect.BACKEND_CPU,
    }


# --- step 1: library ----------------------------------------------------------


def test_library_step_persists_to_user_config(client, tmp_path):
    c, cfg, _db = client
    lib = tmp_path / "my-library"
    r = c.post("/api/setup/library", json={"library_root": str(lib)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    # library_root round-trips through the settings YAML layer.
    assert body["library_root"] == str(lib)
    # Persisted to the per-user config file — NOT the repo config.yaml.
    assert cfg.is_file()
    assert "my-library" in cfg.read_text()
    # And now status reports the library as configured.
    assert c.get("/api/setup/status").json()["steps"]["library"]["configured"] is True


def test_library_step_rejects_empty(client):
    c, _cfg, _db = client
    r = c.post("/api/setup/library", json={"library_root": ""})
    assert r.status_code == 422  # pydantic min_length


# --- step 2: weights ----------------------------------------------------------


def test_weights_plan_is_dry_run(client):
    c, _cfg, _db = client
    r = c.get("/api/setup/weights/plan")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "to_pull" in body and "approx_total_mb" in body
    assert isinstance(body["count"], int)


def test_weights_plan_includes_nudenet_when_opted_in(client):
    c, _cfg, _db = client
    base = c.get("/api/setup/weights/plan?include_nudenet=false").json()
    opted = c.get("/api/setup/weights/plan?include_nudenet=true").json()
    base_keys = {row["key"] for row in base["to_pull"]}
    opted_keys = {row["key"] for row in opted["to_pull"]}
    assert "nudenet" not in base_keys
    assert "nudenet" in opted_keys  # AGPL opt-in surfaced only when requested


def test_weights_pull_skips_network_without_apply_flag(client, monkeypatch):
    c, _cfg, _db = client
    # Make a real pull explode if it were ever called — the apply gate must
    # prevent that entirely.
    import pipeline.weights as weights_mod

    def _boom(*a, **k):
        raise AssertionError("weights.pull must NOT run without the apply flag")

    monkeypatch.setattr(weights_mod, "pull", _boom)
    r = c.post("/api/setup/weights/pull", json={"include_nudenet": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] is False
    assert "plan" in body


def test_weights_pull_runs_when_apply_flag_set(client, monkeypatch):
    c, _cfg, _db = client
    monkeypatch.setenv("MEDIA_PIPELINE_SETUP_APPLY", "1")
    import pipeline.weights as weights_mod

    captured = {}

    def _fake_pull(*, include_optional, include_opt_in, only):
        captured["include_opt_in"] = include_opt_in
        return {"pulled": [], "present": [], "errors": [], "results": []}

    monkeypatch.setattr(weights_mod, "pull", _fake_pull)
    r = c.post("/api/setup/weights/pull", json={"include_nudenet": True})
    assert r.status_code == 200, r.text
    assert r.json()["applied"] is True
    assert captured["include_opt_in"] is True  # opt-in threaded through


# --- step 3: compute ----------------------------------------------------------


def test_compute_detect_reports_backend_and_choices(client):
    c, _cfg, _db = client
    r = c.get("/api/setup/compute/detect")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["detected_backend"] in body["choices"]
    assert detect.BACKEND_CPU in body["choices"]


def test_compute_step_accepts_override(client, monkeypatch):
    c, cfg, _db = client
    r = c.post("/api/setup/compute", json={"backend": detect.BACKEND_CPU})
    assert r.status_code == 200, r.text
    assert r.json()["backend"] == detect.BACKEND_CPU
    assert "local_cpu" in cfg.read_text()


def test_compute_step_rejects_unknown_backend(client):
    c, _cfg, _db = client
    r = c.post("/api/setup/compute", json={"backend": "local_quantum"})
    assert r.status_code == 400


def test_compute_step_defaults_to_detected(client):
    c, _cfg, _db = client
    detected = c.get("/api/setup/compute/detect").json()["detected_backend"]
    r = c.post("/api/setup/compute", json={})
    assert r.status_code == 200, r.text
    assert r.json()["backend"] == detected


# --- step 4: bind + auth ------------------------------------------------------


def test_auth_step_loopback_without_auth_ok(client, monkeypatch):
    c, cfg, _db = client
    monkeypatch.delenv("MEDIA_PIPELINE_AUTH_ENABLED", raising=False)
    r = c.post(
        "/api/setup/auth",
        json={"bind_host": "127.0.0.1", "bind_port": 8000, "enable_auth": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["auth_enabled"] is False
    assert body["admin_seeded"] is False
    assert "8000" in cfg.read_text()


def test_auth_step_nonloopback_requires_auth(client):
    c, _cfg, _db = client
    r = c.post(
        "/api/setup/auth",
        json={"bind_host": "0.0.0.0", "bind_port": 8000, "enable_auth": False},
    )
    assert r.status_code == 400  # §6: open bind needs auth


def test_auth_step_enable_requires_password(client):
    c, _cfg, _db = client
    r = c.post(
        "/api/setup/auth",
        json={"bind_host": "127.0.0.1", "enable_auth": True},
    )
    assert r.status_code == 400


def test_auth_step_persists_hash_not_plaintext(client):
    c, cfg, _db = client
    r = c.post(
        "/api/setup/auth",
        json={
            "bind_host": "127.0.0.1",
            "enable_auth": True,
            "admin_username": "admin",
            "admin_password": "s3cret-pw",
        },
    )
    assert r.status_code == 200, r.text
    text = cfg.read_text()
    assert "s3cret-pw" not in text  # plaintext never persisted
    assert "admin_password_hash" in text


def test_auth_step_seeds_admin_only_with_apply_flag(client, monkeypatch):
    c, _cfg, db = client
    _add_users_table(db)
    monkeypatch.setenv("MEDIA_PIPELINE_SETUP_APPLY", "1")
    r = c.post(
        "/api/setup/auth",
        json={
            "bind_host": "127.0.0.1",
            "enable_auth": True,
            "admin_username": "admin",
            "admin_password": "s3cret-pw",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["admin_seeded"] is True
    # The admin row landed in the TEMP db (never the real catalog).
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT username, role FROM users WHERE username = 'admin'"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("admin", "admin")
    # status now reports the admin as existing.
    assert c.get("/api/setup/status").json()["steps"]["auth"]["admin_exists"] is True


def test_existing_library_is_not_first_run(client):
    """A populated catalog is never first-run, even with no user-config / admin /
    weights configured — an existing install must not be forced back to setup."""
    c, _user_cfg, db = client
    conn = sqlite3.connect(str(db))
    try:
        # Provide a value for every NOT NULL, no-default, non-pk column so the
        # insert is schema-robust as the images table evolves.
        cols = conn.execute("PRAGMA table_info(images)").fetchall()
        required = [col[1] for col in cols if col[3] and col[4] is None and col[5] == 0]
        placeholders = ", ".join("?" for _ in required)
        conn.execute(
            f"INSERT INTO images ({', '.join(required)}) VALUES ({placeholders})",
            [1] * len(required),
        )
        conn.commit()
    finally:
        conn.close()
    assert c.get("/api/setup/status").json()["first_run_needed"] is False


def test_setup_write_locked_once_real_admin_exists(client):
    """Once a loginable admin exists, an unauthenticated setup mutation is 403
    (the provisioned box must not let any peer repoint the library / reseat the
    admin). First-run, the same call is open (covered by the persist test)."""
    c, _user_cfg, db = client
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, is_active) "
            "VALUES ('admin', 'real-bcrypt-or-pbkdf2-hash', 'admin', 1)"
        )
        conn.commit()
    finally:
        conn.close()
    # auth is OFF in the fixture, so there is no principal -> refused.
    r = c.post("/api/setup/library", json={"library_root": "/tmp/x"})
    assert r.status_code == 403
