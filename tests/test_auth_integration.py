"""Integration: the REAL webui.main app with auth ENABLED (audit P1).

The existing auth tests build a throwaway FastAPI app; nothing exercised
``webui.main`` with ``MEDIA_PIPELINE_AUTH_ENABLED=1``. This asserts a protected
route is 401 unauthenticated and 200 after a real login against a seeded admin,
all over the actual app + gate middleware. Fully isolated (temp db + env).
"""

from __future__ import annotations

import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

from pipeline import auth
from pipeline.database import Database
from pipeline.settings import REPO_ROOT, reload_settings


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    db = tmp_path / "catalog.db"
    Database(str(db))  # base schema incl. the users table — never the real catalog
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO users (username, password_hash, role, is_active) VALUES (?,?,?,1)",
        ("admin", auth.hash_password("s3cret-pw"), "admin"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("MEDIA_PIPELINE_PROJECT_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("MEDIA_PIPELINE_DATABASE_PATH", str(db))
    monkeypatch.setenv("MEDIA_PIPELINE_AUTH_ENABLED", "1")  # force the gate ON
    monkeypatch.setenv("MEDIA_PIPELINE_AUTH_SECRET", "stable-test-secret")
    # webui.main captured `db = Database(settings.database_path)` at import, so
    # rebind the settings singleton AND re-import the app so its db binds to THIS
    # temp catalog — then drop it on exit so the binding never leaks to other
    # tests. Without this the fixture silently ran against the real catalog.db
    # (D-TEST-DBBIND).
    monkeypatch.setattr("pipeline.settings.settings", reload_settings())

    sys.modules.pop("webui.main", None)
    # Reset the in-memory login throttle (module-level in webui.auth_routes,
    # keyed by client host) so the suite's prior logins don't 429 this fixture.
    import webui.auth_routes as _ar
    import webui.main

    _ar._LOGIN_ATTEMPTS.clear()

    try:
        yield TestClient(webui.main.app)
    finally:
        sys.modules.pop("webui.main", None)
        reload_settings()


def test_protected_route_401_then_200_after_login(auth_client):
    # Unauthenticated -> 401 on a protected /api route.
    assert auth_client.get("/api/auth/me").status_code == 401

    # Login with the seeded admin -> a bearer token.
    r = auth_client.post(
        "/api/auth/login", json={"username": "admin", "password": "s3cret-pw"}
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert r.json()["role"] == "admin"

    # With the token -> 200 + an authenticated principal.
    r = auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["authenticated"] is True


def test_bad_password_is_401(auth_client):
    r = auth_client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert r.status_code == 401


def test_setup_status_reachable_unauthenticated_when_auth_on(auth_client):
    # The first-run probe stays open even with auth enforced (so a fresh install
    # can bootstrap) — audit P1 exempt path.
    assert auth_client.get("/api/setup/status").status_code == 200
