"""First-run setup wizard API — status + per-step endpoints (Spec F / §7 P0.4).

A self-contained ``APIRouter`` (prefix ``/api/setup``). It is **NOT registered**
here — the orchestrator adds ``app.include_router(routes_setup.router)`` to
``webui/main.py`` (see the lane report's CENTRAL WIRING).

The wizard walks a NEW user through the four P0.4 steps, each backed by an
existing platform seam (no logic duplicated here):

  1. **Library dir** -> written into a per-user YAML config via the settings
     layer (``content_root`` / ``library_root``). No path is hardcoded.
  2. **Model weights** -> ``pipeline.weights.plan()`` size preview +
     ``pipeline.weights.pull()`` (with the NudeNet AGPL opt-in surfaced).
  3. **Compute backend** -> ``pipeline.compute.detect.host_report()`` (the
     detected best) with a user override.
  4. **Bind + auth** -> bind host/port written to the user config; an optional
     admin password written + ``pipeline.bootstrap.seed_admin`` invoked so the
     first user becomes admin (§6).

**First-run-needed check** (``GET /api/setup/status``): true when no library is
configured *or* no admin user exists *or* required weights are missing.

**Safe in tests.** Mirroring ``bootstrap.boot()`` (which only migrates when
``MEDIA_PIPELINE_AUTO_MIGRATE`` is set), the two endpoints with real side
effects are guarded by ``MEDIA_PIPELINE_SETUP_APPLY``:

  * weight ``pull`` only hits the network when the flag is set (otherwise it
    returns a dry-run plan and a ``"skipped"`` marker);
  * the auth step only seeds the admin into the catalog when the flag is set.

So importing/registering this router and exercising the wizard in the test
suite never downloads a model and never mutates the real ``data/catalog.db``.
The per-user config write targets the SAME file the settings authority reads as
its per-user layer (``pipeline.settings._user_config_path()`` —
``platformdirs.user_config_dir``), never the repo's skip-worktree
``config.yaml``. Tests monkeypatch ``pipeline.settings._user_config_path`` so
both the wizard write and the settings read land on a temp file.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from pipeline import auth, weights
from pipeline import settings as settings_mod
from pipeline.compute import detect
from pipeline.settings import reload_settings

router = APIRouter(prefix="/api/setup", tags=["setup"])

# Backend names the compute step accepts as an override (the detector's universe).
_VALID_BACKENDS = frozenset(
    {
        detect.BACKEND_MPS,
        detect.BACKEND_CUDA,
        detect.BACKEND_DIRECTML,
        detect.BACKEND_CPU,
    }
)


# --------------------------------------------------------------------------- #
# Apply-gate + per-user config persistence (never touches config.yaml)
# --------------------------------------------------------------------------- #
def _apply_enabled() -> bool:
    """Whether real side effects (network pull, DB seed) are allowed.

    Off by default so the test suite never downloads weights or mutates the
    catalog; mirrors ``MEDIA_PIPELINE_AUTO_MIGRATE`` in ``bootstrap.boot()``.
    """
    return os.environ.get("MEDIA_PIPELINE_SETUP_APPLY", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _config_target() -> Path:
    """The per-user config file the wizard writes.

    Exactly the file the settings authority reads as its per-user layer
    (``pipeline.settings._user_config_path()`` — the OS-appropriate
    ``platformdirs.user_config_dir`` path), so a write here is picked up on the
    next ``reload_settings()``. The repo's skip-worktree ``config.yaml`` is never
    written. Resolved via the module (not a direct import) so a test that
    monkeypatches ``pipeline.settings._user_config_path`` redirects BOTH the
    wizard write and the settings read to the same temp file.
    """
    return settings_mod._user_config_path()


def _load_user_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _merge_user_config(updates: dict[str, Any]) -> Path:
    """Deep-merge ``updates`` into the per-user config YAML and persist it.

    Returns the file path written. After writing, the settings singleton is
    reloaded so a subsequent ``status`` read reflects the new config.
    """
    path = _config_target()
    path.parent.mkdir(parents=True, exist_ok=True)
    current = _load_user_config(path)

    def _deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
        for key, val in src.items():
            if isinstance(val, dict) and isinstance(dst.get(key), dict):
                _deep_merge(dst[key], val)
            else:
                dst[key] = val
        return dst

    merged = _deep_merge(current, updates)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(merged, f, sort_keys=True)
    reload_settings()
    return path


# --------------------------------------------------------------------------- #
# First-run-needed signals
# --------------------------------------------------------------------------- #
def _library_configured() -> bool:
    """True once the per-user config declares a content/library root.

    The settings layer always *resolves* a content_root (defaulting to
    ``project_root/content``); "configured" here means the USER has made an
    explicit choice persisted to their config file, which is the real first-run
    signal — not the derived default.
    """
    cfg = _load_user_config(_config_target())
    return bool(cfg.get("content_root") or cfg.get("library_root"))


def _admin_exists() -> bool:
    """True if the catalog has at least one admin user (read-only probe)."""
    from pipeline.settings import get_settings

    db_path = str(get_settings().database_path)
    if not Path(db_path).exists():
        return False
    conn = sqlite3.connect(db_path)
    try:
        has_users = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if not has_users:
            return False
        row = conn.execute(
            "SELECT 1 FROM users WHERE role = 'admin' AND is_active = 1 LIMIT 1"
        ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def _has_existing_library() -> bool:
    """True if the catalog already holds images — an existing install, not first-run.

    The wizard is for fresh installs. A populated catalog (e.g. one configured via
    the legacy repo ``config.yaml`` rather than the per-user config) must never be
    forced back through setup, whatever the individual step probes say.
    """
    from pipeline.settings import get_settings

    db_path = str(get_settings().database_path)
    if not Path(db_path).exists():
        return False
    conn = sqlite3.connect(db_path)
    try:
        has_images = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='images'"
        ).fetchone()
        if not has_images:
            return False
        return conn.execute("SELECT 1 FROM images LIMIT 1").fetchone() is not None
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def _real_admin_exists() -> bool:
    """True if a LOGINABLE admin exists — an admin row with a non-empty password
    hash. The migration-012 system placeholder (id=1, blank hash) does NOT count;
    it owns legacy rows but can't authenticate, so the box is still 'unprovisioned'
    until the wizard/env sets a real admin password."""
    from pipeline.settings import get_settings

    db_path = str(get_settings().database_path)
    if not Path(db_path).exists():
        return False
    conn = sqlite3.connect(db_path)
    try:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone():
            return False
        return (
            conn.execute(
                "SELECT 1 FROM users WHERE role='admin' AND is_active=1 "
                "AND password_hash != '' LIMIT 1"
            ).fetchone()
            is not None
        )
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def _require_setup_access(request: Request) -> None:
    """Authorize a setup *mutation*. Open ONLY during genuine first-run.

    Once a real admin exists the install is provisioned: every setup write then
    requires an authenticated admin principal. Otherwise any LAN/tailnet peer
    could repoint the library or overwrite the admin password — even with the
    auth gate off (no principal ⇒ refused). During first-run (no real admin yet)
    the wizard stays open so it can bootstrap.
    """
    if not _real_admin_exists():
        return  # first-run: the wizard must be usable to provision
    principal = getattr(request.state, "principal", None)
    if principal is None or getattr(principal, "role", None) != "admin":
        raise HTTPException(
            status_code=403,
            detail="setup is locked once an admin exists; sign in as an admin "
            "(enable auth) to reconfigure",
        )


# --------------------------------------------------------------------------- #
# GET /api/setup/status — the first-run gate + per-step state
# --------------------------------------------------------------------------- #
@router.get("/status")
async def setup_status() -> dict[str, Any]:
    """First-run-needed + a snapshot of every step's current state.

    ``first_run_needed`` is True when ANY of: no library configured, no admin
    user, or required weights missing — i.e. the wizard should be shown.
    """
    from pipeline.settings import get_settings

    settings = get_settings()
    weights_status = weights.status()
    library_ok = _library_configured()
    admin_ok = _admin_exists()
    weights_ok = bool(weights_status["offline_ready"])
    report = detect.host_report()

    return {
        "first_run_needed": not _has_existing_library()
        and not (library_ok and admin_ok and weights_ok),
        "apply_enabled": _apply_enabled(),
        "config_path": str(_config_target()),
        "steps": {
            "library": {
                "configured": library_ok,
                "content_root": str(settings.content_root),
                "library_root": str(settings.library_root),
            },
            "weights": {
                "offline_ready": weights_ok,
                "required_missing": weights_status["required_missing"],
            },
            "compute": {
                "detected_backend": report.backend,
                "system": report.system,
                "machine": report.machine,
                "apple_silicon": report.apple_silicon,
            },
            "auth": {
                "admin_exists": admin_ok,
                "auth_enabled": auth.auth_enabled(settings.webui_host),
                "bind_host": settings.webui_host,
                "bind_port": settings.webui_port,
            },
        },
    }


# --------------------------------------------------------------------------- #
# Step 1 — library dir
# --------------------------------------------------------------------------- #
class LibraryBody(BaseModel):
    # The library dir the user picks. ``library_root`` is the ingest SCAN root
    # (where the person/media folders live) and is the field the settings YAML
    # layer round-trips today. ``content_root`` (the dir relative DB image paths
    # resolve against) is optional; the settings layer derives it from
    # ``library_root``'s parent default when unset.
    library_root: str = Field(min_length=1)
    content_root: str | None = None


@router.post("/library")
async def setup_library(
    body: LibraryBody, _: None = Depends(_require_setup_access)
) -> dict[str, Any]:
    """Persist the chosen library dir into the per-user config (Spec A layer).

    Writes ``library_root`` (and optional ``content_root``) into the per-user
    config YAML the settings authority reads — no path is hardcoded and the repo
    ``config.yaml`` is never touched. The resolved ``library_root`` is read back
    from the reloaded settings so the wizard confirms the round-trip.

    NOTE (CENTRAL WIRING): ``content_root`` has no mapping in
    ``pipeline/settings._flatten_config_yaml`` yet, so a ``content_root`` written
    here does not change the resolved value until that mapping is added — see the
    lane report. ``library_root`` already round-trips.
    """
    updates: dict[str, Any] = {"library_root": body.library_root}
    if body.content_root:
        updates["content_root"] = body.content_root
    path = _merge_user_config(updates)

    from pipeline.settings import get_settings

    settings = get_settings()
    return {
        "ok": True,
        "config_path": str(path),
        "library_root": str(settings.library_root),
        "content_root": str(settings.content_root),
    }


# --------------------------------------------------------------------------- #
# Step 2 — model weights
# --------------------------------------------------------------------------- #
@router.get("/weights/plan")
async def setup_weights_plan(
    include_optional: bool = True, include_nudenet: bool = False
) -> dict[str, Any]:
    """Dry-run size preview (``weights.plan()``) — no network.

    ``include_nudenet`` surfaces the AGPL opt-in in the preview so the UI can
    show its size before the user commits.
    """
    return weights.plan(
        include_optional=include_optional, include_opt_in=include_nudenet
    )


class WeightsPullBody(BaseModel):
    include_optional: bool = True
    # The NudeNet AGPL opt-in, surfaced explicitly. False == never touch NudeNet.
    include_nudenet: bool = False
    only: list[str] | None = None


@router.post("/weights/pull")
async def setup_weights_pull(
    body: WeightsPullBody, _: None = Depends(_require_setup_access)
) -> dict[str, Any]:
    """Pull missing weights — guarded by ``MEDIA_PIPELINE_SETUP_APPLY``.

    When the apply flag is OFF (the test/default state) this performs NO network
    download: it returns the dry-run plan plus ``"applied": false`` so the UI can
    still preview. When ON, it delegates to ``weights.pull()`` (resumable; the
    AGPL opt-in is honored only when ``include_nudenet``).
    """
    plan = weights.plan(
        include_optional=body.include_optional, include_opt_in=body.include_nudenet
    )
    if not _apply_enabled():
        return {
            "applied": False,
            "reason": "MEDIA_PIPELINE_SETUP_APPLY not set",
            "plan": plan,
        }
    result = weights.pull(
        include_optional=body.include_optional,
        include_opt_in=body.include_nudenet,
        only=body.only,
    )
    return {"applied": True, "result": result}


# --------------------------------------------------------------------------- #
# Step 3 — compute backend
# --------------------------------------------------------------------------- #
@router.get("/compute/detect")
async def setup_compute_detect() -> dict[str, Any]:
    """The detected best backend + the full detection context (for the override)."""
    report = detect.host_report()
    return {
        "detected_backend": report.backend,
        "system": report.system,
        "machine": report.machine,
        "apple_silicon": report.apple_silicon,
        "available_providers": report.available_providers,
        "choices": sorted(_VALID_BACKENDS),
    }


class ComputeBody(BaseModel):
    # None == accept the auto-detected backend; otherwise a user override.
    backend: str | None = None


@router.post("/compute")
async def setup_compute(
    body: ComputeBody, _: None = Depends(_require_setup_access)
) -> dict[str, Any]:
    """Persist the chosen compute backend (detected default or user override)."""
    backend = body.backend or detect.host_report().backend
    if backend not in _VALID_BACKENDS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown backend {backend!r}; choices: {sorted(_VALID_BACKENDS)}",
        )
    path = _merge_user_config({"compute": {"backend": backend}})
    return {"ok": True, "backend": backend, "config_path": str(path)}


# --------------------------------------------------------------------------- #
# Step 4 — bind host/port + optional auth
# --------------------------------------------------------------------------- #
def _seed_admin_row(username: str, password_hash: str) -> None:
    """Idempotently create/refresh the first admin in the configured catalog.

    Mirrors ``bootstrap.seed_admin``'s SQL but takes an already-computed hash
    and a username directly — so the wizard never mutates the process
    environment (which would leak credentials into later requests/tests and flip
    the global auth gate). Requires the ``users`` table (migration 012).
    """
    from pipeline.settings import get_settings

    conn = sqlite3.connect(str(get_settings().database_path))
    try:
        has_users = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if not has_users:
            raise RuntimeError("users table missing — run migration 012 first")
        row = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET password_hash = ?, role = 'admin', is_active = 1 "
                "WHERE id = ?",
                (password_hash, row[0]),
            )
        else:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, is_active) "
                "VALUES (?, ?, 'admin', 1)",
                (username, password_hash),
            )
        conn.commit()
    finally:
        conn.close()


class BindAuthBody(BaseModel):
    bind_host: str = Field(default="127.0.0.1", min_length=1)
    bind_port: int = Field(default=8000, ge=1, le=65535)
    enable_auth: bool = False
    admin_username: str = Field(default="admin", min_length=1)
    # Required only when enable_auth is True; never echoed back.
    admin_password: str | None = None


@router.post("/auth")
async def setup_auth(
    body: BindAuthBody, _: None = Depends(_require_setup_access)
) -> dict[str, Any]:
    """Persist bind host/port and optionally create the first admin (§6).

    Bind is non-localhost? Auth MUST be enabled (uncensored content makes
    open-bind-without-auth a non-starter). When ``enable_auth`` is set, the
    admin password is persisted to the per-user config; the actual catalog seed
    (``bootstrap.seed_admin``) only runs when ``MEDIA_PIPELINE_SETUP_APPLY`` is
    set, so tests never mutate the real DB.
    """
    is_loopback = body.bind_host in ("127.0.0.1", "::1", "localhost")
    if not is_loopback and not body.enable_auth:
        raise HTTPException(
            status_code=400,
            detail="a non-localhost bind requires auth to be enabled (§6)",
        )
    if body.enable_auth and not body.admin_password:
        raise HTTPException(
            status_code=400, detail="admin_password is required when enable_auth is set"
        )

    updates: dict[str, Any] = {
        "webui": {"host": body.bind_host, "port": body.bind_port}
    }
    pw_hash: str | None = None
    if body.enable_auth:
        # Persist the auth intent + credentials into the per-user config (the
        # launcher reads the ``auth`` block on next boot). The password is stored
        # ONLY as a hash — never plaintext.
        assert body.admin_password is not None
        pw_hash = auth.hash_password(body.admin_password)
        updates["auth"] = {
            "enabled": True,
            "admin_username": body.admin_username,
            "admin_password_hash": pw_hash,
            # Stable token-signing secret so auth survives restarts without a
            # plaintext password in env (read by bootstrap.apply_persisted_auth_env).
            "secret": secrets.token_hex(32),
        }
    path = _merge_user_config(updates)

    seeded = False
    if body.enable_auth and _apply_enabled():
        assert pw_hash is not None
        _seed_admin_row(body.admin_username, pw_hash)
        seeded = True

    return {
        "ok": True,
        "config_path": str(path),
        "bind_host": body.bind_host,
        "bind_port": body.bind_port,
        "auth_enabled": body.enable_auth,
        "admin_seeded": seeded,
    }
