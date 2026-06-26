"""Per-user owner_id row scoping (audit C1).

Two layers:
  * unit — the central ``webui.scoping`` primitives (viewer rule, query filter,
    object-level check), including a real SQLAlchemy session.
  * integration — the REAL ``webui.main`` app with auth ON: a non-admin sees
    only their own rows + legacy (NULL-owner) rows; an admin sees everything;
    a cross-tenant detail fetch reads as 404.

Scoping is DORMANT on a single-user / auth-off install (the viewer resolves to
None -> no-op). These tests force auth on + a non-admin principal to exercise it.
"""

from __future__ import annotations

import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

from pipeline import auth
from pipeline.auth import Principal
from pipeline.database import Database, Image, Tag
from pipeline.settings import REPO_ROOT, reload_settings
from webui import scoping


# --------------------------------------------------------------------------- #
# unit — the scoping primitives
# --------------------------------------------------------------------------- #
class _Req:
    """Minimal stand-in for a Starlette request carrying ``state.principal``."""

    def __init__(self, principal):
        self.state = type("S", (), {"principal": principal})()


def test_viewer_owner_id_rules():
    assert scoping.viewer_owner_id(None) is None  # no request
    assert scoping.viewer_owner_id(_Req(None)) is None  # unauthenticated
    # admin is unscoped (sees everything)
    assert scoping.viewer_owner_id(_Req(Principal(1, "admin", "admin"))) is None
    # a non-admin scopes to their own user_id
    assert scoping.viewer_owner_id(_Req(Principal(7, "bob", "user"))) == 7


def test_can_view_rules():
    admin = _Req(Principal(1, "admin", "admin"))
    bob = _Req(Principal(7, "bob", "user"))

    class Row:
        def __init__(self, owner):
            self.owner_id = owner

    assert scoping.can_view(Row(None), None) is True  # unscoped: all visible
    assert scoping.can_view(Row(99), admin) is True  # admin: all visible
    assert scoping.can_view(Row(None), bob) is True  # legacy row visible
    assert scoping.can_view(Row(7), bob) is True  # own row
    assert scoping.can_view(Row(8), bob) is False  # foreign row hidden


def test_scope_query_filters_session(tmp_path):
    db = Database(str(tmp_path / "c.db"))
    session = db.get_session()
    try:
        session.add_all(
            [
                Image(path="legacy.jpg", owner_id=None),
                Image(path="bob.jpg", owner_id=7),
                Image(path="alice.jpg", owner_id=9),
            ]
        )
        session.commit()

        bob = _Req(Principal(7, "bob", "user"))
        scoped = scoping.scope_query(session.query(Image), Image, bob).all()
        assert {i.path for i in scoped} == {"legacy.jpg", "bob.jpg"}  # own + legacy

        # admin / auth-off -> no-op, sees all three
        assert scoping.scope_query(session.query(Image), Image, None).count() == 3
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# integration — the real app with auth ON
# --------------------------------------------------------------------------- #
@pytest.fixture
def scoped_client(tmp_path, monkeypatch):
    db = tmp_path / "catalog.db"
    Database(str(db))  # base schema incl. users + images — never the real catalog
    conn = sqlite3.connect(str(db))
    for name, role, pw in (("admin", "admin", "admin-pw"), ("bob", "user", "bob-pw")):
        conn.execute(
            "INSERT INTO users (username, password_hash, role, is_active) VALUES (?,?,?,1)",
            (name, auth.hash_password(pw), role),
        )
    conn.commit()
    admin_id = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
    bob_id = conn.execute("SELECT id FROM users WHERE username='bob'").fetchone()[0]
    conn.close()

    # Seed images via the ORM so the model's Python-side column defaults apply
    # (raw INSERTs skip them and trip NOT NULL on e.g. nudenet_checked/flagged).
    session = Database(str(db)).get_session()
    images = {
        "legacy": Image(path="legacy.jpg", owner_id=None, processed=True, person="ava"),
        "bob": Image(
            path="bob.jpg",
            owner_id=bob_id,
            processed=True,
            person="bob_person",
        ),
        "admin": Image(
            path="admin.jpg",
            owner_id=admin_id,
            processed=True,
            person="admin_person",
        ),
    }
    session.add_all(images.values())
    session.flush()  # assign image ids for the tag FKs
    # Tags drive the aggregate (tag-table) scoping: every image has a
    # `content_type` tag; ONLY admin's image has a `rating` tag — so a non-admin
    # viewer must not see the `rating` category at all.
    session.add_all(
        [
            Tag(image_id=images["legacy"].id, category="content_type", value="x"),
            Tag(image_id=images["bob"].id, category="content_type", value="y"),
            Tag(image_id=images["admin"].id, category="content_type", value="z"),
            Tag(image_id=images["admin"].id, category="rating", value="nsfw"),
        ]
    )
    session.commit()
    ids = {label: img.id for label, img in images.items()}
    session.close()

    monkeypatch.setenv("MEDIA_PIPELINE_PROJECT_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("MEDIA_PIPELINE_DATABASE_PATH", str(db))
    monkeypatch.setenv("MEDIA_PIPELINE_AUTH_ENABLED", "1")
    monkeypatch.setenv("MEDIA_PIPELINE_AUTH_SECRET", "stable-test-secret")
    # reload_settings() refreshes get_settings() but does NOT rebind the module
    # singleton webui.main captured via `from pipeline.settings import settings`,
    # so rebind it explicitly to the tmp-db settings before importing the app.
    monkeypatch.setattr("pipeline.settings.settings", reload_settings())

    # Re-import webui.main so its module-level db binds to THIS temp catalog, and
    # drop it again on exit so the binding never leaks into other tests.
    sys.modules.pop("webui.main", None)
    # Reset the in-memory login throttle: it is module-level in webui.auth_routes
    # (keyed by client host, not popped with webui.main) so the suite's many
    # logins otherwise accumulate into a spurious 429.
    import webui.auth_routes as _ar
    import webui.main

    _ar._LOGIN_ATTEMPTS.clear()

    try:
        yield TestClient(webui.main.app), ids
    finally:
        sys.modules.pop("webui.main", None)
        reload_settings()


def _login(client, username, password):
    r = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_admin_sees_all_images(scoped_client):
    client, ids = scoped_client
    headers = _login(client, "admin", "admin-pw")
    r = client.get("/api/images", headers=headers)
    assert r.status_code == 200, r.text
    got = {img["id"] for img in r.json()["images"]}
    assert got == set(ids.values())  # legacy + bob + admin


def test_non_admin_sees_only_own_plus_legacy(scoped_client):
    client, ids = scoped_client
    headers = _login(client, "bob", "bob-pw")
    r = client.get("/api/images", headers=headers)
    assert r.status_code == 200, r.text
    got = {img["id"] for img in r.json()["images"]}
    assert got == {ids["legacy"], ids["bob"]}
    assert ids["admin"] not in got  # never another user's row


def test_non_admin_detail_foreign_is_404(scoped_client):
    client, ids = scoped_client
    headers = _login(client, "bob", "bob-pw")
    # own + legacy: visible
    assert client.get(f"/api/images/{ids['bob']}", headers=headers).status_code == 200
    assert (
        client.get(f"/api/images/{ids['legacy']}", headers=headers).status_code == 200
    )
    # foreign: 404 (existence not revealed)
    assert client.get(f"/api/images/{ids['admin']}", headers=headers).status_code == 404


# --------------------------------------------------------------------------- #
# integration — aggregate dashboard endpoints (D-OWNER-AGG)
# --------------------------------------------------------------------------- #
def test_stats_scoped_by_owner(scoped_client):
    """/api/stats counts reflect the viewer: image + people via scope_query,
    tag_categories via scope_by_owner_via (the tag-table join path)."""
    client, _ = scoped_client
    admin = client.get("/api/stats", headers=_login(client, "admin", "admin-pw")).json()
    bob = client.get("/api/stats", headers=_login(client, "bob", "bob-pw")).json()

    assert admin["total_images"] == 3  # admin: all rows
    assert bob["total_images"] == 2  # bob: own + legacy
    assert admin["people_count"] == 3
    assert bob["people_count"] == 2
    assert admin["tag_categories"] == 2  # content_type + rating
    assert bob["tag_categories"] == 1  # rating tag lives only on admin's image


def test_pipeline_scoped_by_owner(scoped_client):
    client, _ = scoped_client
    admin = client.get("/api/pipeline", headers=_login(client, "admin", "admin-pw"))
    bob = client.get("/api/pipeline", headers=_login(client, "bob", "bob-pw"))
    assert admin.json()["total"] == 3
    assert bob.json()["total"] == 2


def test_facets_scoped_by_owner(scoped_client):
    client, _ = scoped_client
    admin = client.get(
        "/api/facets", headers=_login(client, "admin", "admin-pw")
    ).json()
    bob = client.get("/api/facets", headers=_login(client, "bob", "bob-pw")).json()

    assert set(admin["people"]) == {"ava", "bob_person", "admin_person"}
    assert set(bob["people"]) == {"ava", "bob_person"}  # admin's person hidden
    # the `rating` category exists only on admin's image -> invisible to bob
    assert "rating" in admin["categories"]
    assert "rating" not in bob["categories"]
    assert "content_type" in bob["categories"]


def test_directories_scoped_by_owner(scoped_client):
    client, _ = scoped_client

    def by_person(role, pw):
        r = client.get("/api/stats/directories", headers=_login(client, role, pw))
        return {row["key"]: row["image_count"] for row in r.json()["by_person"]}

    assert by_person("admin", "admin-pw") == {
        "ava": 1,
        "bob_person": 1,
        "admin_person": 1,
    }
    assert by_person("bob", "bob-pw") == {"ava": 1, "bob_person": 1}  # admin's hidden
