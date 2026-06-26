"""Auth endpoints + the per-request authorization gate for the web UI (Spec B / §6).

Two pieces, both wired by ``webui.main``:

  - ``router`` — ``POST /api/auth/login`` (username+password -> bearer token),
    ``POST /api/auth/logout`` (client-side token drop), ``GET /api/auth/me``.
  - ``AuthGateMiddleware`` — enforces auth on protected paths. **Opt-in:** when
    ``auth.auth_enabled(bind_host)`` is False (the default dev config — no admin
    password, loopback bind) the middleware is a pure pass-through, so the
    existing web test suite needs no auth headers and stays green. When enabled,
    every ``/api/*``, ``/media/*``, ``/image-content/*`` path requires a valid
    bearer token except the login/health exemptions below.

The gate is middleware (not a per-route ``Depends``) deliberately: it covers the
~50 existing ``@app.get`` routes and the wave-2 routers uniformly without editing
each decorator, and it is provably inert when auth is disabled.
"""

from __future__ import annotations

import sqlite3
import time

from fastapi import APIRouter, HTTPException
from fastapi import Request as FastAPIRequest
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from pipeline import auth
from pipeline.settings import get_settings

# Paths that stay open even when auth is enabled: the login endpoint itself and a
# couple of unauthenticated liveness/probe routes the shell needs pre-login.
_EXEMPT_PATHS = frozenset(
    {
        "/api/auth/login",
        "/api/auth/status",
        # Read-only first-run probe — must be reachable pre-login so the setup
        # wizard can bootstrap an install that has auth enabled before any admin
        # exists (otherwise it 401s and can never provision). Mutating setup
        # endpoints stay protected and carry their own admin guard.
        "/api/setup/status",
    }
)
# Only these prefixes are guarded; the SPA shell + assets stay public so the
# login page can load. Mirrors main.py's _RESERVED_PREFIXES.
_PROTECTED_PREFIXES = ("/api/", "/media/", "/image-content/")

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str


def _lookup_user(username: str) -> tuple[int, str, str, str] | None:
    """Return (id, username, role, password_hash) for an active user, or None."""
    conn = sqlite3.connect(str(get_settings().database_path))
    try:
        has_users = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if not has_users:
            return None
        row = conn.execute(
            "SELECT id, username, role, password_hash FROM users "
            "WHERE username = ? AND is_active = 1",
            (username,),
        ).fetchone()
        return tuple(row) if row else None
    finally:
        conn.close()


# --- admin authz + login throttle (audit P1) ------------------------------- #
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
_LOGIN_WINDOW_S = 300.0
_LOGIN_MAX = 10


def require_admin(request: FastAPIRequest) -> None:
    """Dependency for destructive / corpus-mutating routes.

    When auth is enforced, require an admin principal (403 otherwise). When auth
    is OFF (single-user/dev) it allows — there are no non-admin users to escalate.
    Closes the multi-user privilege-escalation gap (audit P1)."""
    if not auth.auth_enabled(get_settings().webui_host):
        return
    principal = getattr(request.state, "principal", None)
    if principal is None or not getattr(principal, "is_admin", False):
        raise HTTPException(status_code=403, detail="admin privileges required")


def _throttle_login(request: FastAPIRequest) -> None:
    """Per-client fixed-window login throttle (audit P1). In-memory + best-effort;
    front a real limiter at the proxy for production."""
    now = time.monotonic()
    client = request.client.host if request.client else "unknown"
    hits = [t for t in _LOGIN_ATTEMPTS.get(client, []) if now - t < _LOGIN_WINDOW_S]
    if len(hits) >= _LOGIN_MAX:
        raise HTTPException(
            status_code=429, detail="too many login attempts; wait and retry"
        )
    hits.append(now)
    _LOGIN_ATTEMPTS[client] = hits


@router.get("/status")
async def auth_status():
    """Whether auth is enforced (UI uses this to decide to show a login gate)."""
    return {"auth_enabled": auth.auth_enabled(get_settings().webui_host)}


@router.post("/login")
async def login(body: LoginBody, request: FastAPIRequest):
    """Exchange username+password for a signed bearer token."""
    _throttle_login(request)
    found = _lookup_user(body.username)
    if not found or not auth.verify_password(body.password, found[3]):
        raise HTTPException(status_code=401, detail="invalid credentials")
    user_id, username, role, _ = found
    token = auth.issue_token(user_id, username, role)
    return {"access_token": token, "token_type": "bearer", "role": role}


@router.post("/logout")
async def logout():
    """Stateless tokens — logout is a client-side drop. Provided for symmetry."""
    return {"ok": True}


@router.get("/me")
async def me(request: FastAPIRequest):
    """The current principal, set by the gate. 401 if unauthenticated + enforced."""
    principal = getattr(request.state, "principal", None)
    if principal is None:
        if auth.auth_enabled(get_settings().webui_host):
            raise HTTPException(status_code=401, detail="not authenticated")
        return {"authenticated": False, "auth_enabled": False}
    return {
        "authenticated": True,
        "auth_enabled": True,
        "user_id": principal.user_id,
        "username": principal.username,
        "role": principal.role,
    }


class AuthGateMiddleware(BaseHTTPMiddleware):
    """Enforce bearer auth on protected paths — only when auth is enabled.

    Pass-through when ``auth.auth_enabled(bind_host)`` is False. The decision is
    re-read per request (cheap env + string checks) so an env toggle takes effect
    without a rebuild. On a protected path with no/invalid token, returns 401
    before the route runs. A valid token sets ``request.state.principal``.
    """

    async def dispatch(self, request: FastAPIRequest, call_next):
        # Re-evaluated per request so tests/env toggles take effect without a
        # rebuild; cheap (env + string checks).
        if not auth.auth_enabled(get_settings().webui_host):
            return await call_next(request)

        path = request.url.path
        protected = path.startswith(_PROTECTED_PREFIXES) and path not in _EXEMPT_PATHS
        if not protected:
            return await call_next(request)

        token = auth.extract_bearer(request.headers.get("authorization"))
        principal = auth.verify_token(token) if token else None
        if principal is None:
            return JSONResponse(
                status_code=401, content={"detail": "not authenticated"}
            )
        request.state.principal = principal
        return await call_next(request)
