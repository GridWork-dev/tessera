"""User-interface preferences — a versioned JSON blob (Wave 1 foundation).

Display-only chrome state: nav order, hidden modules, dashboard layout, theme
choice. Stored as ONE JSON file in the per-user config dir, separate from the
typed settings authority (settings.py owns paths/ports; this owns chrome). A
single versioned blob (not typed columns) because the module registry will churn
and prefs are never queried.

Tests monkeypatch ``_ui_prefs_path`` onto a temp file (mirrors
pipeline.settings._user_config_path), so reads/writes never touch real config.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import platformdirs

APP_NAME = "media-pipeline"
PREFS_VERSION = 1

DEFAULT_PREFS: dict[str, Any] = {
    "version": PREFS_VERSION,
    "ui": {
        "nav": {"order": [], "hidden": []},
        "dashboard": {"cards": [], "hidden": []},
        "modules": {"enabled": {}},
        "theme": "pigment",
    },
}


def _ui_prefs_path() -> Path:
    return Path(platformdirs.user_config_dir(APP_NAME)) / "ui_prefs.json"


def load_prefs() -> dict[str, Any]:
    """Read the prefs blob; return a fresh DEFAULT_PREFS if absent or corrupt."""
    path = _ui_prefs_path()
    if not path.is_file():
        return copy.deepcopy(DEFAULT_PREFS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return copy.deepcopy(DEFAULT_PREFS)
    if not isinstance(data, dict):
        return copy.deepcopy(DEFAULT_PREFS)
    data.setdefault("version", PREFS_VERSION)
    data.setdefault("ui", copy.deepcopy(DEFAULT_PREFS["ui"]))
    return data


def save_prefs(prefs: dict[str, Any]) -> dict[str, Any]:
    """Persist the prefs blob atomically; return what was written."""
    path = _ui_prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    out = dict(prefs)
    out.setdefault("version", PREFS_VERSION)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, indent=2), encoding="utf-8")
    tmp.replace(path)
    return out
