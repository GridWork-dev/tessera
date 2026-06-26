"""HTTP tests for the auth-ENABLED path: login, protected-route 401/200, status.

Builds a minimal app wiring the real auth router + AuthGateMiddleware against a
TEMP db (never the real catalog). The default-dev OPEN path is covered by the
existing webui suite (which imports webui.main with auth disabled and uses no
auth headers) — we don't duplicate that here.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pipeline import bootstrap
from pipeline.database import Database
from pipeline.settings import REPO_ROOT, reload_settings


@pytest.fixture
def enabled_client(monkeypatch):
    """An app with auth ENABLED, a seeded admin, and one protected route."""
    d = tempfile.mkdtemp()
    db = Path(d) / "catalog.db"
    Database(str(db))
    conn = sqlite3.connect(str(db))
    conn.executescript(
        (REPO_ROOT / "data" / "migrations" / "002_collections_labels.sql").read_text()
    )
    conn.commit()
    conn.close()

    # Point settings at the temp db and force auth on with a known admin pw.
    monkeypatch.setenv("MEDIA_PIPELINE_DATABASE_PATH", str(db))
    monkeypatch.setenv("MEDIA_PIPELINE_PROJECT_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("MEDIA_PIPELINE_AUTH_ENABLED", "1")
    monkeypatch.setenv("MEDIA_PIPELINE_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("MEDIA_PIPELINE_ADMIN_PASSWORD", "s3cret-pw")
    monkeypatch.setenv("MEDIA_PIPELINE_AUTH_SECRET", "route-test-secret")
    reload_settings()  # so auth_routes' settings.database_path sees the temp db

    bootstrap.run_pending_migrations(db, do_backup=False)
    bootstrap.seed_admin(db)

    # Import after settings are pointed at the temp db.
    from webui.auth_routes import AuthGateMiddleware
    from webui.auth_routes import router as auth_router

    app = FastAPI()
    app.add_middleware(AuthGateMiddleware)
    app.include_router(auth_router)

    @app.get("/api/protected")
    async def protected():
        return {"ok": True}

    try:
        yield TestClient(app)
    finally:
        reload_settings()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(str(db) + suffix)
            except OSError:
                pass


def test_status_reports_enabled(enabled_client):
    r = enabled_client.get("/api/auth/status")
    assert r.status_code == 200
    assert r.json()["auth_enabled"] is True


def test_protected_route_401_without_token(enabled_client):
    r = enabled_client.get("/api/protected")
    assert r.status_code == 401


def test_login_then_protected_route_200(enabled_client):
    r = enabled_client.post(
        "/api/auth/login", json={"username": "admin", "password": "s3cret-pw"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "admin"
    token = body["access_token"]

    r2 = enabled_client.get(
        "/api/protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert r2.status_code == 200
    assert r2.json() == {"ok": True}


def test_login_bad_password_401(enabled_client):
    r = enabled_client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert r.status_code == 401


def test_login_unknown_user_401(enabled_client):
    r = enabled_client.post(
        "/api/auth/login", json={"username": "nobody", "password": "x"}
    )
    assert r.status_code == 401


def test_me_with_token(enabled_client):
    token = enabled_client.post(
        "/api/auth/login", json={"username": "admin", "password": "s3cret-pw"}
    ).json()["access_token"]
    r = enabled_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["authenticated"] is True
    assert body["username"] == "admin"
    assert body["role"] == "admin"


def test_login_endpoint_exempt_from_gate(enabled_client):
    # /api/auth/login must be reachable WITHOUT a token even when auth is on.
    r = enabled_client.post(
        "/api/auth/login", json={"username": "admin", "password": "s3cret-pw"}
    )
    assert r.status_code != 401
