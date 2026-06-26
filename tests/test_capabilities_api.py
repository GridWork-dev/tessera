from fastapi.testclient import TestClient
from sqlalchemy import text

from pipeline.database import Database
from webui.routes_capabilities import _has_geo, _has_videos


def _client():
    import webui.main as m

    return TestClient(m.app)


def test_capabilities_response_shape(monkeypatch):
    monkeypatch.delenv("MP_FACES_ENABLED", raising=False)
    r = _client().get("/api/capabilities")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"faces", "geo", "video", "license"}
    assert all(isinstance(v, bool) for v in body.values())
    assert body["faces"] is False  # off by default
    assert body["license"] is True  # license system always available


def test_capabilities_faces_env_on(monkeypatch):
    monkeypatch.setenv("MP_FACES_ENABLED", "1")
    assert _client().get("/api/capabilities").json()["faces"] is True


def test_has_videos_data_presence():
    """video gate is data-presence: false with no videos, true once one exists."""
    db = Database(":memory:")
    assert _has_videos(db) is False
    with db.get_session() as s:
        s.execute(text("DROP TABLE IF EXISTS videos"))
        s.execute(text("CREATE TABLE videos (id INTEGER PRIMARY KEY)"))
        s.execute(text("INSERT INTO videos (id) VALUES (1)"))
        s.commit()
    assert _has_videos(db) is True


def test_has_geo_data_presence():
    """geo gate is data-presence: false with no geocoded rows, true once a place exists."""
    db = Database(":memory:")
    assert _has_geo(db) is False
    with db.get_session() as s:
        s.execute(text("DROP TABLE IF EXISTS places"))
        s.execute(text("CREATE TABLE places (id INTEGER PRIMARY KEY)"))
        s.execute(text("INSERT INTO places (id) VALUES (1)"))
        s.commit()
    assert _has_geo(db) is True
