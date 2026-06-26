"""Ed25519 offline license tokens — sign (issuer) + verify (app).

Real signature verification replacing the old forgeable shape-check. A token is
``MPL-<TIER>-<OPAQUE>`` where ``<OPAQUE>`` is the base64url of ``payload||signature``:

  * ``payload``  = compact UTF-8 JSON of the signed claims (sorted keys, no spaces)
  * ``signature`` = the 64-byte Ed25519 signature over exactly those payload bytes

The app verifies against a **baked-in public key** (``PUBLIC_KEY_B64`` below). The
**private** key never lives here — it stays in the issuing tool / Polar webhook,
read from env or file (see ``scripts/issue_license.py``).

Claims (the signed payload):

  * ``tier``         (str, required)  — e.g. ``"pro"``
  * ``max_version``  (int, required)  — highest app MAJOR version this license
                                        grants Pro on (perpetual-per-major).
  * ``issued_at``    (int, required)  — unix seconds the token was issued.
  * ``customer_id``  (str, optional)  — opaque buyer id (for support/audit).
  * ``expires``      (int, optional)  — unix seconds; if present and in the past,
                                        the token is rejected (community fallback).

Verification is **pure, offline, never raises**: any malformed / forged / tampered
/ expired input returns ``None`` so callers fail safe to the community tier. This
module deliberately knows nothing about ``ProFeature`` / app wiring — that lives in
``pipeline/licensing.py``.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# --------------------------------------------------------------------------- #
# Baked-in PUBLIC verification key (Ed25519 raw, base64).                      #
#                                                                             #
# This is a public key — safe to ship in the binary. The matching PRIVATE key #
# is NOT in the repo; it is generated/held by the license issuer. To rotate   #
# for production, generate a fresh keypair (see scripts/issue_license.py      #
# --gen-key) and replace this constant with the printed public key.           #
# --------------------------------------------------------------------------- #
PUBLIC_KEY_B64 = "AkH62U/IPaLabz0+3U2rouH2ZDnCcYm8glZlnaajdXc="

TOKEN_PREFIX = "MPL"
SIGNATURE_LEN = 64  # Ed25519 signatures are always 64 bytes.
REQUIRED_CLAIMS = ("tier", "max_version", "issued_at")


@dataclass(frozen=True)
class LicenseClaims:
    """The verified, signed claims carried by a token."""

    tier: str
    max_version: int
    issued_at: int
    customer_id: str | None = None
    expires: int | None = None

    def is_expired(self, *, now: int | None = None) -> bool:
        if self.expires is None:
            return False
        return (now if now is not None else int(time.time())) >= self.expires


def _b64url_encode(raw: bytes) -> str:
    """URL-safe base64 without padding (stable, prefix-free of ``-``/``+``)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _encode_payload(claims: LicenseClaims) -> bytes:
    """Compact, deterministic JSON of the claims (the bytes that get signed)."""
    obj: dict[str, object] = {
        "tier": claims.tier,
        "max_version": int(claims.max_version),
        "issued_at": int(claims.issued_at),
    }
    if claims.customer_id is not None:
        obj["customer_id"] = claims.customer_id
    if claims.expires is not None:
        obj["expires"] = int(claims.expires)
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode_payload(payload: bytes) -> LicenseClaims | None:
    try:
        obj = json.loads(payload.decode("utf-8"))
    except ValueError, UnicodeDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    for key in REQUIRED_CLAIMS:
        if key not in obj:
            return None
    try:
        tier = str(obj["tier"])
        max_version = int(obj["max_version"])
        issued_at = int(obj["issued_at"])
    except TypeError, ValueError:
        return None
    customer_id = obj.get("customer_id")
    if customer_id is not None and not isinstance(customer_id, str):
        return None
    expires_raw = obj.get("expires")
    expires: int | None = None
    if expires_raw is not None:
        try:
            expires = int(expires_raw)
        except TypeError, ValueError:
            return None
    return LicenseClaims(
        tier=tier,
        max_version=max_version,
        issued_at=issued_at,
        customer_id=customer_id,
        expires=expires,
    )


def sign_token(claims: LicenseClaims, private_key: Ed25519PrivateKey) -> str:
    """ISSUER side: produce ``MPL-<TIER>-<OPAQUE>`` for ``claims``.

    Used only by ``scripts/issue_license.py`` (and tests). The app never calls
    this — it has no private key.
    """
    payload = _encode_payload(claims)
    signature = private_key.sign(payload)
    opaque = _b64url_encode(payload + signature)
    return f"{TOKEN_PREFIX}-{claims.tier.upper()}-{opaque}"


def _load_public_key(public_key_b64: str | None = None) -> Ed25519PublicKey:
    raw = base64.b64decode(public_key_b64 or PUBLIC_KEY_B64)
    return Ed25519PublicKey.from_public_bytes(raw)


def verify_token(
    token: str | None, *, public_key_b64: str | None = None, now: int | None = None
) -> LicenseClaims | None:
    """APP side: verify a token's signature and return its claims, or ``None``.

    Returns ``None`` (fail safe) for any unknown / malformed / tampered / expired
    token. Never raises. The signed ``tier`` claim is the authority; the human
    ``<TIER>`` segment in the prefix is cosmetic and is re-derived from the
    payload, so a mismatched/forged prefix cannot grant anything.
    """
    if not token:
        return None
    parts = token.strip().split("-", 2)
    if len(parts) != 3:
        return None
    prefix, _tier_segment, opaque = parts
    if prefix != TOKEN_PREFIX or not opaque:
        return None
    try:
        blob = _b64url_decode(opaque)
    except Exception:  # noqa: BLE001 - any decode failure => reject
        return None
    if len(blob) <= SIGNATURE_LEN:
        return None
    payload, signature = blob[:-SIGNATURE_LEN], blob[-SIGNATURE_LEN:]
    try:
        _load_public_key(public_key_b64).verify(signature, payload)
    except InvalidSignature, ValueError:
        return None
    claims = _decode_payload(payload)
    if claims is None:
        return None
    if claims.is_expired(now=now):
        return None
    return claims


def generate_keypair() -> tuple[str, str]:
    """Make a fresh Ed25519 keypair as ``(private_b64, public_b64)`` raw strings.

    Helper for ``scripts/issue_license.py --gen-key``. The private string is a
    secret — store it in the issuer's env/file, never the repo.
    """
    sk = Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives import serialization

    priv = sk.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    pub = sk.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(priv).decode("ascii"), base64.b64encode(pub).decode("ascii")


def load_private_key_b64(private_key_b64: str) -> Ed25519PrivateKey:
    """Build an Ed25519 private key from a raw base64 string (issuer side)."""
    raw = base64.b64decode(private_key_b64)
    return Ed25519PrivateKey.from_private_bytes(raw)


__all__ = [
    "PUBLIC_KEY_B64",
    "TOKEN_PREFIX",
    "LicenseClaims",
    "generate_keypair",
    "load_private_key_b64",
    "sign_token",
    "verify_token",
]
