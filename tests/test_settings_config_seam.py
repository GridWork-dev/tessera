"""Regression for the staging/live config seam.

``settings_from_config_file`` must honor the documented precedence where
``MEDIA_PIPELINE_*`` env is HIGHEST — above an explicit ``--config`` file. A file
that shadowed ``MEDIA_PIPELINE_DATABASE_PATH`` (repo ``config.yaml`` winning over a
staging env) caused a live-DB write incident: the batch CLI wrote to the canonical
``data/catalog.db`` even though the staging env pointed elsewhere. These tests pin
the fix (env wins) and the fallback (file drives when no env override is set).
"""

from pathlib import Path

import yaml

from pipeline.settings import settings_from_config_file


def _write_config(tmp_path: Path, db_path: str) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "project_root": str(tmp_path),
                "database": {"path": db_path},
                "webui": {"port": 9999},
            }
        )
    )
    return cfg


def test_env_overrides_config_file_database_path(tmp_path, monkeypatch):
    # File says one DB; env says another. Env must win (the breach guard).
    cfg = _write_config(tmp_path, str(tmp_path / "from_file.db"))
    monkeypatch.setenv("MEDIA_PIPELINE_DATABASE_PATH", str(tmp_path / "from_env.db"))

    s = settings_from_config_file(cfg)

    assert s.database_path.name == "from_env.db"


def test_config_file_drives_when_env_absent(tmp_path, monkeypatch):
    # No env override -> the explicit --config file drives the run.
    cfg = _write_config(tmp_path, str(tmp_path / "from_file.db"))
    monkeypatch.delenv("MEDIA_PIPELINE_DATABASE_PATH", raising=False)

    s = settings_from_config_file(cfg)

    assert s.database_path.name == "from_file.db"
