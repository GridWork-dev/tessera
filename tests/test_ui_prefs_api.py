from fastapi.testclient import TestClient


def _client():
    import webui.main as m

    return TestClient(m.app)


def test_ui_prefs_get_default(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pipeline.ui_prefs._ui_prefs_path", lambda: tmp_path / "ui_prefs.json"
    )
    r = _client().get("/api/ui-prefs")
    assert r.status_code == 200
    assert r.json()["ui"]["theme"] == "pigment"


def test_ui_prefs_put_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pipeline.ui_prefs._ui_prefs_path", lambda: tmp_path / "ui_prefs.json"
    )
    c = _client()
    r = c.put("/api/ui-prefs", json={"version": 1, "ui": {"theme": "slate"}})
    assert r.status_code == 200
    assert c.get("/api/ui-prefs").json()["ui"]["theme"] == "slate"
