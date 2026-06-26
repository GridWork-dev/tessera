"""Portable, typed settings — the single config authority (Spec A).

Replaces the scattered ``yaml.safe_load(config.yaml)`` reads with one validated
``pydantic-settings`` object. OS-appropriate default dirs come from
``platformdirs``; every path is resolvable on any box and inside a frozen app
bundle (no machine-specific absolute paths baked in).

Resolution precedence (lowest -> highest):

  1. shipped ``defaults.yaml`` (committed, repo root) — portable defaults
  2. per-user config at ``platformdirs.user_config_dir("media-pipeline")/config.yaml``
  3. the repo's ``config.yaml`` IF present — back-compat for the maintainer's box
     (it is ``git skip-worktree`` with this box's private absolute paths; we READ
     it but never write or commit it)
  4. ``MEDIA_PIPELINE_*`` environment variables (highest)

Back-compat contract: with NO config.yaml and NO env, the defaults reproduce
this repo's current layout — ``project_root`` = the repo root (derived from this
file's location), ``content_root`` = ``project_root/content``, ``database_path``
= ``project_root/data/catalog.db``, cache/thumbs/grids under ``project_root/data``
— so the live launchd server and the test suite keep working unchanged.

Import the module-level ``settings`` singleton; call ``get_settings()`` (or
``reload_settings()``) when a fresh read is needed (e.g. tests).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import platformdirs
import yaml
from pydantic import Field, computed_field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

APP_NAME = "media-pipeline"

# Repo/app root derived from this file: pipeline/settings.py -> repo = parent.parent.
# This is the default project_root and the home of the committed defaults.yaml +
# the (optional, skip-worktree) config.yaml. Works repo-relative today; an
# installed app overrides project_root via env / user config.
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULTS_YAML = REPO_ROOT / "defaults.yaml"
REPO_CONFIG_YAML = REPO_ROOT / "config.yaml"


def _user_config_path() -> Path:
    """Per-user config file location (OS-appropriate via platformdirs)."""
    return Path(platformdirs.user_config_dir(APP_NAME)) / "config.yaml"


def _flatten_config_yaml(raw: dict[str, Any]) -> dict[str, Any]:
    """Map the nested config.yaml / defaults.yaml shape onto flat setting fields.

    The on-disk YAML keeps its historical nested shape (``database.path``,
    ``webui.host``, ``paths.grids``, ``library_root``); this lifts the handful of
    keys the settings object exposes into flat keys, leaving every other block
    (vlm, compute, ffmpeg, faces, ...) untouched under ``raw`` for the modules
    that still read those directly.
    """
    out: dict[str, Any] = {}
    if not raw:
        return out

    if "project_root" in raw:
        out["project_root"] = raw["project_root"]
    # content_root is the dir relative DB image paths resolve against; library_root
    # is the ingest SCAN root (where person folders live). On this box
    # library_root = <content_root>/library. Both are flat top-level keys (the
    # first-run wizard writes them via the per-user config).
    if "content_root" in raw:
        out["content_root"] = raw["content_root"]
    if "library_root" in raw:
        out["library_root"] = raw["library_root"]

    database = raw.get("database") or {}
    if "path" in database:
        out["database_path"] = database["path"]

    paths = raw.get("paths") or {}
    if "grids" in paths:
        out["grids_dir"] = paths["grids"]

    webui = raw.get("webui") or {}
    if "host" in webui:
        out["webui_host"] = webui["host"]
    if "port" in webui:
        out["webui_port"] = webui["port"]
    if "cors_origins" in webui:
        out["cors_origins"] = webui["cors_origins"]

    return out


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class _YamlLayerSource(PydanticBaseSettingsSource):
    """Settings source: defaults.yaml -> user config -> repo config.yaml.

    Later files override earlier ones; env vars (handled by the higher-priority
    env source) override all of these.
    """

    def get_field_value(self, field, field_name):  # pragma: no cover - unused
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for path in (DEFAULTS_YAML, _user_config_path(), REPO_CONFIG_YAML):
            merged.update(_flatten_config_yaml(_load_yaml(path)))
        return merged


class Settings(BaseSettings):
    """Typed, env-overridable config authority.

    Env prefix ``MEDIA_PIPELINE_`` — e.g. ``MEDIA_PIPELINE_DATABASE_PATH``,
    ``MEDIA_PIPELINE_WEBUI_PORT``. Path fields accept absolute or
    project_root-relative values; the validator resolves relatives against
    ``project_root`` and exposes absolute ``Path`` objects.
    """

    model_config = SettingsConfigDict(
        env_prefix="MEDIA_PIPELINE_",
        extra="ignore",
    )

    # --- roots (defaults reproduce the current box layout) ---
    project_root: Path = Field(default=REPO_ROOT)
    # content_root: dir that relative DB image paths resolve against. Default
    # project_root/content (matches pipeline.paths.CONTENT_ROOT today). This is
    # the single seam resolve_image_path() goes through — see pipeline/paths.py.
    content_root: Path | None = Field(default=None)
    # library_root: ingest SCAN root (person folders). Default content_root/library.
    library_root: Path | None = Field(default=None)

    # --- data paths (relative -> resolved against project_root) ---
    database_path: Path = Field(default=Path("data/catalog.db"))
    cache_dir: Path | None = Field(default=None)  # default data/cache
    thumbs_dir: Path | None = Field(default=None)  # default data/cache/thumbs
    grids_dir: Path = Field(default=Path("data/grids"))
    models_cache_dir: Path | None = Field(default=None)  # default models/

    # --- webui ---
    webui_host: str = Field(default="127.0.0.1")
    webui_port: int = Field(default=8000)
    cors_origins: list[str] = Field(default_factory=list)

    # --- commerce (issuer-only) ---
    # Polar webhook signing secret. UNSET in the shipped customer app, so the
    # order.paid minting endpoint self-gates to 503 there (license issuance is an
    # operator-only concern). Env: MEDIA_PIPELINE_POLAR_WEBHOOK_SECRET.
    polar_webhook_secret: str | None = Field(default=None)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Precedence high -> low: init kwargs, env, dotenv, the YAML layer.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            _YamlLayerSource(settings_cls),
        )

    @model_validator(mode="after")
    def _resolve_paths(self) -> Settings:
        root = self.project_root.expanduser()
        if not root.is_absolute():
            root = (REPO_ROOT / root).resolve()
        self.project_root = root

        def _abs(p: Path | None, default_rel: str) -> Path:
            if p is None:
                p = Path(default_rel)
            p = p.expanduser()
            if not p.is_absolute():
                p = root / p
            return p

        self.content_root = _abs(self.content_root, "content")
        # library_root default lives under the resolved content_root, mirroring
        # the current box (content/library).
        if self.library_root is None:
            self.library_root = self.content_root / "library"
        else:
            lib = self.library_root.expanduser()
            self.library_root = lib if lib.is_absolute() else root / lib
        self.database_path = _abs(self.database_path, "data/catalog.db")
        self.cache_dir = _abs(self.cache_dir, "data/cache")
        # thumbs default lives under the resolved cache dir, mirroring main.py.
        if self.thumbs_dir is None:
            self.thumbs_dir = self.cache_dir / "thumbs"
        else:
            self.thumbs_dir = _abs(self.thumbs_dir, "data/cache/thumbs")
        self.grids_dir = _abs(self.grids_dir, "data/grids")
        # Default to the existing repo-relative ``models/`` dir where the ONNX
        # taggers live, so first-run weight pulls and the inference loaders share
        # one root (audit P0-3). Override with MEDIA_PIPELINE_MODELS_CACHE_DIR.
        self.models_cache_dir = _abs(self.models_cache_dir, "models")
        return self

    # --- OS-appropriate dirs (platformdirs); used by later specs for logs/state. ---
    @computed_field  # type: ignore[prop-decorator]
    @property
    def user_log_dir(self) -> Path:
        return Path(platformdirs.user_log_dir(APP_NAME))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def user_state_dir(self) -> Path:
        return Path(platformdirs.user_state_dir(APP_NAME))


def settings_from_config_file(config_path: str | Path) -> Settings:
    """Build a Settings from an explicit YAML file (the CLI ``--config`` path).

    Used by the batch CLIs that accept ``--config`` so an out-of-tree config (or
    a test's temp config) still drives the run. Layers the same defaults.yaml
    underneath the given file, then applies MEDIA_PIPELINE_* env on top. Falls
    back to the standard precedence when the path is absent.
    """
    config_path = Path(config_path)
    base = _flatten_config_yaml(_load_yaml(DEFAULTS_YAML))
    base.update(_flatten_config_yaml(_load_yaml(config_path)))
    # Honor the documented precedence: MEDIA_PIPELINE_* env is HIGHEST. These YAML
    # values are passed as init kwargs, which OUTRANK the env source in
    # pydantic-settings — so a key set in both would let the file shadow the env.
    # Drop any base key an env var already overrides, leaving the env source to set
    # it. Without this an out-of-tree `--config` silently shadows e.g.
    # MEDIA_PIPELINE_DATABASE_PATH, writing to the wrong DB (the staging/live seam).
    env_prefix = Settings.model_config.get("env_prefix", "")
    env_overridden = {
        key[len(env_prefix) :].lower()
        for key in os.environ
        if env_prefix and key.startswith(env_prefix)
    }
    base = {k: v for k, v in base.items() if k.lower() not in env_overridden}
    return Settings(**base)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton (resolved once per process)."""
    return Settings()


def reload_settings() -> Settings:
    """Drop the cache, re-resolve, and rebind the module-level ``settings``
    singleton (tests / config changes).

    Rebinding ``settings`` here means callers that read ``pipeline.settings
    .settings`` see refreshed values after a reload. Note: a module that did
    ``from pipeline.settings import settings`` holds its OWN name binding and
    must be re-imported to pick up the new object (see the test fixtures that
    pop ``webui.main`` from ``sys.modules`` — D-TEST-DBBIND).
    """
    global settings
    get_settings.cache_clear()
    settings = get_settings()
    return settings


# Module-level singleton — import this for the common case.
settings = get_settings()
