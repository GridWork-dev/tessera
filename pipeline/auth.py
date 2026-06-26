"""Password auth + per-request authorization (Spec B + §6).

Design goals (in order):

1. **Opt-in enforcement.** With the default dev config — no admin password set and
   a loopback bind — auth is OFF and every endpoint stays open, so the existing
   web test suite passes unchanged (no auth headers required). Enforcement turns
   on only when an admin password IS configured, or the bind is non-localhost
   (uncensored content makes open-bind-without-auth a non-starter — §6).
2. **No hand-rolled crypto.** Password hashing uses a vetted KDF: argon2-cffi or
   bcrypt if installed, else the stdlib OpenSSL ``hashlib.pbkdf2_hmac`` (the same
   PBKDF2 primitive Django's default hasher uses). Hashes are self-describing
   (``algo$...``) so a stronger backend can be adopted later without a data
   migration.
3. **Stateless bearer sessions.** Login returns a signed, expiring token (HMAC
   over the stdlib — no JWT dependency). The token is verified per request; no
   server-side session store to corrupt or scale.

Config (env, since Spec A's ``settings`` does not yet carry auth fields — see the
lane's CENTRAL WIRING note to promote these to ``pipeline/settings.py``):

  - ``MEDIA_PIPELINE_ADMIN_PASSWORD``  — if set, auth is enabled and bootstrap
    creates/updates the admin user from it.
  - ``MEDIA_PIPELINE_ADMIN_USERNAME``  — admin username (default ``admin``).
  - ``MEDIA_PIPELINE_AUTH_SECRET``      — token-signing secret. Defaults to a
    value derived from the admin password hash if unset (stable across restarts
    as long as the password is unchanged).
  - ``MEDIA_PIPELINE_AUTH_ENABLED``     — explicit override (``1``/``0``); wins
    over the password/bind heuristic when set.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass

# Vetted-KDF preference order; fall back to stdlib PBKDF2 (still a vetted
# primitive, not hand-rolled). Detected once at import.
try:  # pragma: no cover - depends on optional dep
    from argon2 import PasswordHasher as _Argon2Hasher

    _ARGON2 = _Argon2Hasher()
except Exception:  # pragma: no cover
    _ARGON2 = None

try:  # pragma: no cover - depends on optional dep
    import bcrypt as _bcrypt
except Exception:  # pragma: no cover
    _bcrypt = None

_PBKDF2_ROUNDS = 240_000
_TOKEN_TTL_SECONDS = 12 * 60 * 60  # 12h sessions


# --------------------------------------------------------------------------- #
# Password hashing (self-describing ``algo$...`` strings)
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    """Hash a plaintext password with the strongest available vetted KDF."""
    if not password:
        raise ValueError("password must be non-empty")
    if _ARGON2 is not None:  # pragma: no cover - optional dep
        return "argon2$" + _ARGON2.hash(password)
    if _bcrypt is not None:  # pragma: no cover - optional dep
        digest = _bcrypt.hashpw(password.encode(), _bcrypt.gensalt())
        return "bcrypt$" + digest.decode()
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return (
        f"pbkdf2_sha256${_PBKDF2_ROUNDS}$"
        f"{base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"
    )


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verify of a plaintext password against a stored hash."""
    if not stored or "$" not in password + stored:
        return False
    algo, _, rest = stored.partition("$")
    try:
        if algo == "argon2":  # pragma: no cover - optional dep
            if _ARGON2 is None:
                return False
            try:
                return _ARGON2.verify(rest, password)
            except Exception:
                return False
        if algo == "bcrypt":  # pragma: no cover - optional dep
            if _bcrypt is None:
                return False
            return _bcrypt.checkpw(password.encode(), rest.encode())
        if algo == "pbkdf2_sha256":
            rounds_s, salt_b64, dk_b64 = rest.split("$")
            salt = base64.b64decode(salt_b64)
            expected = base64.b64decode(dk_b64)
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(rounds_s))
            return hmac.compare_digest(dk, expected)
    except Exception:
        return False
    return False


# --------------------------------------------------------------------------- #
# Config / gate
# --------------------------------------------------------------------------- #
def _env(name: str) -> str | None:
    val = os.environ.get(name)
    return val if val not in (None, "") else None


def admin_username() -> str:
    return _env("MEDIA_PIPELINE_ADMIN_USERNAME") or "admin"


def admin_password() -> str | None:
    return _env("MEDIA_PIPELINE_ADMIN_PASSWORD")


def _is_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "::1", "localhost")


def auth_enabled(bind_host: str | None = None) -> bool:
    """Decide whether enforcement is ON.

    OFF by default (dev): no admin password and a loopback bind. ON when an
    admin password is configured, or the bind is non-localhost, or the explicit
    ``MEDIA_PIPELINE_AUTH_ENABLED`` override is truthy. The explicit override
    wins over the heuristic so an operator can force either state.
    """
    override = _env("MEDIA_PIPELINE_AUTH_ENABLED")
    if override is not None:
        return override.strip().lower() in ("1", "true", "yes", "on")
    if admin_password() is not None:
        return True
    if bind_host is not None and not _is_loopback(bind_host):
        return True
    return False


def auth_secret() -> bytes:
    """Token-signing secret. Explicit env wins; else derive from the admin
    password so it is stable across restarts without persisting a secret."""
    explicit = _env("MEDIA_PIPELINE_AUTH_SECRET")
    if explicit:
        return explicit.encode()
    pw = admin_password()
    if pw:
        return hashlib.sha256(("mp-auth-secret:" + pw).encode()).digest()
    # No stable secret available. Safe only when auth is OFF (tokens are never
    # minted). If auth is forced on without a secret or password, fail LOUDLY
    # rather than return a per-call random secret that invalidates every token
    # the instant it is issued (a silent self-DoS — audit P2).
    if auth_enabled():
        raise RuntimeError(
            "auth is enabled but neither MEDIA_PIPELINE_AUTH_SECRET nor "
            "MEDIA_PIPELINE_ADMIN_PASSWORD is set — refusing to sign tokens with "
            "a non-persistent secret"
        )
    return secrets.token_bytes(32)


# --------------------------------------------------------------------------- #
# Stateless bearer tokens (HMAC, stdlib — no JWT dependency)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Principal:
    """The authenticated caller resolved from a token."""

    user_id: int
    username: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_token(
    user_id: int, username: str, role: str, *, ttl: int = _TOKEN_TTL_SECONDS
) -> str:
    """Issue a signed ``user_id.username.role.expiry`` bearer token."""
    expiry = int(time.time()) + ttl
    payload = f"{user_id}.{username}.{role}.{expiry}"
    sig = hmac.new(auth_secret(), payload.encode(), hashlib.sha256).digest()
    return f"{_b64u(payload.encode())}.{_b64u(sig)}"


def verify_token(token: str) -> Principal | None:
    """Verify a bearer token; return the Principal or None if invalid/expired."""
    if not token or token.count(".") != 1:
        return None
    payload_b64, sig_b64 = token.split(".")
    try:
        payload = _b64u_decode(payload_b64)
        sig = _b64u_decode(sig_b64)
    except Exception:
        return None
    expected = hmac.new(auth_secret(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        user_id_s, username, role, expiry_s = payload.decode().split(".")
        if int(expiry_s) < int(time.time()):
            return None
        return Principal(user_id=int(user_id_s), username=username, role=role)
    except Exception:
        return None


def extract_bearer(authorization_header: str | None) -> str | None:
    """Pull the token out of an ``Authorization: Bearer <token>`` header."""
    if not authorization_header:
        return None
    parts = authorization_header.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None
