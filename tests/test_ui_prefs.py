import os

import pytest

from pipeline import ui_prefs


def test_load_prefs_defaults_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_prefs, "_ui_prefs_path", lambda: tmp_path / "ui_prefs.json")
    p = ui_prefs.load_prefs()
    assert p["version"] == ui_prefs.PREFS_VERSION
    assert p["ui"]["theme"] == "pigment"
    assert p["ui"]["nav"] == {"order": [], "hidden": []}


def test_save_then_load_roundtrip(tmp_path, monkeypatch):
    target = tmp_path / "sub" / "ui_prefs.json"
    monkeypatch.setattr(ui_prefs, "_ui_prefs_path", lambda: target)
    ui_prefs.save_prefs(
        {
            "version": 1,
            "ui": {"theme": "slate", "nav": {"order": ["videos"], "hidden": []}},
        }
    )
    assert target.is_file()
    p = ui_prefs.load_prefs()
    assert p["ui"]["theme"] == "slate"
    assert p["ui"]["nav"]["order"] == ["videos"]


def test_load_prefs_tolerates_corrupt_file(tmp_path, monkeypatch):
    target = tmp_path / "ui_prefs.json"
    target.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(ui_prefs, "_ui_prefs_path", lambda: target)
    assert ui_prefs.load_prefs()["ui"]["theme"] == "pigment"


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses file permission bits, so chmod 0o000 stays readable",
)
def test_load_prefs_tolerates_unreadable_file(tmp_path, monkeypatch):
    """An OSError on read (file present but unreadable) falls back to DEFAULT_PREFS.

    Covers the OSError half of load_prefs' ``except (JSONDecodeError, OSError)``
    (the corrupt-file test only exercises the JSONDecodeError half).
    """
    target = tmp_path / "ui_prefs.json"
    target.write_text('{"version": 1, "ui": {"theme": "slate"}}', encoding="utf-8")
    target.chmod(0o000)
    monkeypatch.setattr(ui_prefs, "_ui_prefs_path", lambda: target)
    try:
        prefs = ui_prefs.load_prefs()
    finally:
        # Restore perms so tmp_path teardown can unlink the file.
        target.chmod(0o644)
    assert prefs["ui"]["theme"] == "pigment"
