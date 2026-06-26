import sqlite3
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from pipeline.labels.store import LabelStore
from pipeline.migrations import apply_migration

MIG = Path("data/migrations/013_label_sets.sql")


@contextmanager
def _client(tmp_path):
    """Yield a TestClient whose get_store dep points at a fresh temp DB.

    The override is set on the process-global ``webui.main.app`` and MUST be
    cleared afterwards, or it leaks into every later test that touches the app
    (e.g. test_label_filter's TestClient). Clearing in a finally keeps the
    override scoped to one test.
    """
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE images (id INTEGER PRIMARY KEY, rating TEXT);
        CREATE TABLE user_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_id INTEGER NOT NULL, category TEXT NOT NULL, value TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')), owner_id INTEGER,
            UNIQUE(image_id, category, value)
        );
        INSERT INTO images (id, rating) VALUES (1, NULL);
        """
    )
    conn.commit()
    apply_migration(conn, MIG)
    conn.close()
    import webui.main as m
    from webui import routes_labels

    m.app.dependency_overrides[routes_labels.get_store] = lambda: LabelStore(db)
    try:
        yield TestClient(m.app)
    finally:
        m.app.dependency_overrides.clear()


def test_list_sets_has_rating(tmp_path):
    with _client(tmp_path) as c:
        r = c.get("/api/label-sets")
        assert r.status_code == 200
        assert any(s["name"] == "Rating" for s in r.json())


def test_create_set_add_value_assign(tmp_path):
    with _client(tmp_path) as c:
        sid = c.post(
            "/api/label-sets", json={"name": "Project", "single_select": False}
        ).json()["id"]
        c.post(f"/api/label-sets/{sid}/values", json={"value": "alpha"})
        c.post("/api/label-sets/images/1", json={"set_id": sid, "value": "alpha"})
        labels = c.get("/api/label-sets/images/1").json()
        assert any(lbl["value"] == "alpha" and lbl["set_id"] == sid for lbl in labels)


def test_patch_set_renames_and_reorders(tmp_path):
    with _client(tmp_path) as c:
        sid = c.post("/api/label-sets", json={"name": "Project"}).json()["id"]
        r = c.patch(
            f"/api/label-sets/{sid}",
            json={"name": "Status", "single_select": True, "sort_order": -5},
        )
        assert r.status_code == 200
        s = next(x for x in c.get("/api/label-sets").json() if x["id"] == sid)
        assert s["name"] == "Status"
        assert s["single_select"] == 1
        # Reordered before the seeded Rating set (sort_order 0).
        order = [x["name"] for x in c.get("/api/label-sets").json()]
        assert order.index("Status") < order.index("Rating")


def test_remove_value_deletes_the_value(tmp_path):
    """DELETE /api/label-sets/{set_id}/values/{value_id} drops the value."""
    with _client(tmp_path) as c:
        sid = c.post("/api/label-sets", json={"name": "Project"}).json()["id"]
        vid = c.post(f"/api/label-sets/{sid}/values", json={"value": "alpha"}).json()[
            "id"
        ]
        c.post(f"/api/label-sets/{sid}/values", json={"value": "beta"})
        # Sanity: both present.
        before = next(s for s in c.get("/api/label-sets").json() if s["id"] == sid)
        assert {v["value"] for v in before["values"]} == {"alpha", "beta"}

        r = c.delete(f"/api/label-sets/{sid}/values/{vid}")
        assert r.status_code == 200
        after = next(s for s in c.get("/api/label-sets").json() if s["id"] == sid)
        assert {v["value"] for v in after["values"]} == {"beta"}


def test_delete_set_removes_it(tmp_path):
    """DELETE /api/label-sets/{set_id} removes the whole set."""
    with _client(tmp_path) as c:
        sid = c.post("/api/label-sets", json={"name": "Temp"}).json()["id"]
        assert any(s["id"] == sid for s in c.get("/api/label-sets").json())
        r = c.delete(f"/api/label-sets/{sid}")
        assert r.status_code == 200
        assert all(s["id"] != sid for s in c.get("/api/label-sets").json())


def test_unassign_removes_label_from_image(tmp_path):
    """DELETE /api/label-sets/images/{image_id}/{label_id} unassigns a label."""
    with _client(tmp_path) as c:
        sid = c.post("/api/label-sets", json={"name": "Project"}).json()["id"]
        c.post(f"/api/label-sets/{sid}/values", json={"value": "alpha"})
        lid = c.post(
            "/api/label-sets/images/1", json={"set_id": sid, "value": "alpha"}
        ).json()["id"]
        assert any(lbl["id"] == lid for lbl in c.get("/api/label-sets/images/1").json())

        r = c.delete(f"/api/label-sets/images/1/{lid}")
        assert r.status_code == 200
        assert all(lbl["id"] != lid for lbl in c.get("/api/label-sets/images/1").json())


def test_assign_to_bogus_set_id_is_404(tmp_path):
    """assign() maps the store's ValueError (unknown set) to HTTP 404."""
    with _client(tmp_path) as c:
        r = c.post("/api/label-sets/images/1", json={"set_id": 999999, "value": "x"})
        assert r.status_code == 404
