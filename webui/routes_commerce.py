"""Commerce: in-app License panel API + (issuer-only) Polar order.paid webhook.

Two surfaces, both wired by ``webui.main``:

  * ``GET/POST/DELETE /api/license`` — the in-app license panel. Read the resolved
    entitlements (offline), save a verified token to ``license.key`` in the project
    root, or remove it. Verification is Ed25519 vs the baked-in public key
    (``pipeline.license_tokens``) — a LOCAL save, never a network submit. All three
    fail safe: a bad token never writes, a missing file never errors.

  * ``POST /api/commerce/webhook/polar`` — ISSUER-ONLY infrastructure that mints OUR
    Ed25519 license token when Polar reports a paid order. It SELF-GATES: with no
    ``polar_webhook_secret`` configured (the shipped customer app) it returns 503, so
    minting is impossible there. With a secret, it verifies the Standard-Webhooks
    HMAC signature over the raw body FIRST and rejects (401) anything unverified —
    NEVER mints on an unverified payload. Issuance is idempotent via an append-only
    JSONL ledger keyed on ``order_id`` (webhooks retry; one order -> one token). The
    minted token is NOT returned in the HTTP body — delivery (email/portal) is a
    deferred concern.

Provider seam: the Polar-specific header/event parsing lives in a thin adapter
(``_parse_polar_event``) so swapping to a fallback merchant-of-record later is a
localized change.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from fastapi import Request as FastAPIRequest
from pydantic import BaseModel

from pipeline import licensing
from pipeline.license_tokens import (
    LicenseClaims,
    load_private_key_b64,
    sign_token,
    verify_token,
)
from pipeline.licensing import KEY_FILENAME, ProFeature
from pipeline.settings import get_settings

# Env name for the issuer's Ed25519 PRIVATE signing key (raw base64). Read ONLY
# from env in the webhook — never hard-coded, never committed. Mirrors the name
# scripts/issue_license.py uses so the two issuers share one key.
PRIVATE_KEY_ENV = "MEDIA_PIPELINE_LICENSE_PRIVATE_KEY"

router = APIRouter(tags=["commerce"])


# --------------------------------------------------------------------------- #
# License panel — in-app entitlement view + local token save/clear.            #
# --------------------------------------------------------------------------- #
def _project_root() -> Path:
    """Where ``license.key`` lives (the dir pipeline.licensing reads from)."""
    return get_settings().project_root


def _license_path() -> Path:
    return _project_root() / KEY_FILENAME


def _status_payload() -> dict:
    """Resolve the current license offline and shape the panel response.

    Never raises — ``load_license`` fails safe to community for any
    bad/missing/forged token, so the panel always renders.
    """
    status = licensing.load_license(project_root=_project_root())
    return {
        "tier": status.tier.value,
        "features": {
            "bulk_export": status.has(ProFeature.BULK_EXPORT),
            "remote_compute_routing": status.has(ProFeature.REMOTE_COMPUTE_ROUTING),
            "priority_support": status.has(ProFeature.PRIORITY_SUPPORT),
        },
        "detail": status.detail,
        "max_version": _max_version(),
    }


def _max_version() -> int | None:
    """The signed ``max_version`` of the active token, or None if no valid token.

    Reads the same token ``load_license`` reads (env then ``license.key``) and
    returns its verified ``max_version`` claim. None when there is no
    valid/verifiable token.
    """
    # _read_token + verify_token are the same primitives load_license uses; reuse
    # them so the panel reports exactly what the resolver acted on.
    token = licensing._read_token(_project_root())
    claims = verify_token(token)
    return claims.max_version if claims is not None else None


class SaveLicenseBody(BaseModel):
    token: str


@router.get("/api/license")
async def get_license() -> dict:
    """Resolved entitlements for the license panel. Read-only, offline, never raises."""
    return _status_payload()


@router.post("/api/license")
async def save_license(body: SaveLicenseBody) -> dict:
    """Save a token to ``license.key`` IFF it verifies. Local save, not a submit.

    A token that verifies (Ed25519 vs the baked-in public key) is written to the
    project-root ``license.key`` and the license is re-resolved. An invalid /
    forged / empty token writes NOTHING and returns 400.
    """
    token = (body.token or "").strip()
    if verify_token(token) is None:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "error": "token failed verification"},
        )
    _license_path().write_text(token + "\n", encoding="utf-8")
    status = licensing.load_license(project_root=_project_root())
    return {"ok": True, "tier": status.tier.value, "detail": status.detail}


@router.delete("/api/license")
async def delete_license() -> dict:
    """Remove ``license.key`` if present; revert to community. Never errors."""
    path = _license_path()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # A best-effort clear: even if the unlink fails we report community (the
        # next load may still read it, but we never brick or 500 the panel).
        pass
    return {"ok": True, "tier": licensing.Tier.COMMUNITY.value}


# --------------------------------------------------------------------------- #
# Polar webhook (issuer-only) — verify -> filter -> mint -> idempotent ledger. #
# --------------------------------------------------------------------------- #
def _ledger_path() -> Path:
    """Append-only issuance ledger (gitignored). Operator-local, never committed."""
    return _project_root() / "outputs" / "licenses" / "ledger.jsonl"


def _ledger_lookup(order_id: str) -> dict | None:
    """Return the existing ledger entry for ``order_id``, or None. Never raises."""
    path = _ledger_path()
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get("order_id") == order_id:
                    return entry
    except OSError:
        return None
    return None


def _ledger_append(entry: dict) -> None:
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")


def _decode_secret(secret: str) -> bytes:
    """The HMAC key bytes from a Standard-Webhooks / Polar signing secret.

    Polar/Standard-Webhooks secrets are ``whsec_<base64>``; the HMAC key is the
    base64-DECODED part after the ``whsec_`` prefix. We tolerate a missing prefix
    and a non-base64 secret (fall back to raw UTF-8 bytes) so an operator who
    pastes a plain shared secret still works.
    """
    raw = secret
    if raw.startswith("whsec_"):
        raw = raw[len("whsec_") :]
    try:
        return base64.b64decode(raw)
    except Exception:  # noqa: BLE001 - any decode failure -> raw bytes
        return secret.encode("utf-8")


def _verify_polar_signature(secret: str, headers, body: bytes) -> bool:
    """Verify the Standard-Webhooks (Polar) HMAC over the RAW body.

    Signed content is ``{webhook-id}.{webhook-timestamp}.{body}``; the signature
    is HMAC-SHA256 keyed by the (base64-decoded) secret, base64-encoded. The
    ``webhook-signature`` header is a space-separated list of ``v1,<b64sig>``
    entries (key rotation); we accept if ANY entry matches, with a constant-time
    compare. Missing headers / no match -> False (caller rejects with 401).
    """
    webhook_id = headers.get("webhook-id")
    timestamp = headers.get("webhook-timestamp")
    signature_header = headers.get("webhook-signature")
    if not webhook_id or not timestamp or not signature_header:
        return False

    signed = webhook_id.encode("utf-8") + b"." + timestamp.encode("utf-8") + b"." + body
    expected = base64.b64encode(
        hmac.new(_decode_secret(secret), signed, hashlib.sha256).digest()
    ).decode("ascii")

    for part in signature_header.split():
        # Each part is ``<version>,<b64sig>`` (e.g. ``v1,abc...``). Compare the
        # base64 portion in constant time.
        _, _, candidate = part.partition(",")
        if candidate and hmac.compare_digest(candidate, expected):
            return True
    return False


def _parse_polar_event(payload: dict) -> dict | None:
    """Adapter: pull the fields we need out of a Polar webhook payload.

    Returns ``{event_type, order_id, customer_id, email, major_version}`` or None
    if the shape is unusable. Kept thin so a fallback merchant-of-record adapter
    is a localized swap. Polar wraps the entity under ``data``; the major version
    is a product metadata field.
    """
    if not isinstance(payload, dict):
        return None
    event_type = payload.get("type")
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return None

    order_id = data.get("id")
    customer_id = data.get("customer_id")
    email = (
        data.get("customer", {}).get("email")
        if isinstance(data.get("customer"), dict)
        else None
    )

    # major_version lives in the purchased product's metadata.
    product = data.get("product") or {}
    metadata = product.get("metadata") if isinstance(product, dict) else None
    major_version = None
    if isinstance(metadata, dict):
        major_version = metadata.get("major_version")
    try:
        major_version = int(major_version) if major_version is not None else None
    except TypeError, ValueError:
        major_version = None

    return {
        "event_type": event_type,
        "order_id": str(order_id) if order_id is not None else None,
        "customer_id": str(customer_id) if customer_id is not None else None,
        "email": email,
        "major_version": major_version,
    }


@router.post("/api/commerce/webhook/polar")
async def polar_webhook(request: FastAPIRequest) -> Response:
    """ISSUER-ONLY: mint a perpetual-per-major Pro token on a paid Polar order.

    Self-gating: no ``polar_webhook_secret`` configured -> 503 (the shipped app).
    With a secret: verify the Standard-Webhooks HMAC over the raw body FIRST
    (401 on failure), then act only on ``order.paid``. Issuance is idempotent via
    the order_id ledger. The minted token is NOT returned in the response body.
    """
    secret = get_settings().polar_webhook_secret
    if not secret:
        raise HTTPException(status_code=503, detail="webhook minting not configured")

    raw_body = await request.body()
    if not _verify_polar_signature(secret, request.headers, raw_body):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except ValueError, UnicodeDecodeError:
        # Signature verified but body is not JSON — ack so Polar stops retrying.
        return Response(
            content='{"ok":true,"status":"ignored"}', media_type="application/json"
        )

    event = _parse_polar_event(payload)
    if event is None or event["event_type"] != "order.paid":
        return Response(
            content='{"ok":true,"status":"ignored"}', media_type="application/json"
        )

    order_id = event["order_id"]
    if not order_id:
        return Response(
            content='{"ok":true,"status":"ignored"}', media_type="application/json"
        )

    # Idempotency: a retried webhook for the same order re-uses the minted token.
    existing = _ledger_lookup(order_id)
    if existing is not None:
        return Response(
            content='{"ok":true,"status":"already_issued"}',
            media_type="application/json",
        )

    private_key_b64 = os.environ.get(PRIVATE_KEY_ENV)
    if not private_key_b64:
        # Secret set but no signing key on this host — cannot mint. 500 so the
        # operator notices misconfiguration (vs the customer-app 503).
        raise HTTPException(status_code=500, detail="signing key not configured")

    major_version = event["major_version"]
    if major_version is None:
        # A paid order with no product major_version is un-mintable; ack to stop
        # retries (operator should fix the product metadata).
        return Response(
            content='{"ok":true,"status":"missing_major_version"}',
            media_type="application/json",
        )

    private_key = load_private_key_b64(private_key_b64)
    issued_at = int(time.time())
    claims = LicenseClaims(
        tier="pro",
        max_version=major_version,
        issued_at=issued_at,
        customer_id=event["customer_id"],
        expires=None,  # perpetual-per-major
    )
    token = sign_token(claims, private_key)

    _ledger_append(
        {
            "order_id": order_id,
            "customer_id": event["customer_id"],
            "email": event["email"],
            "major_version": major_version,
            "token": token,
            "issued_at": issued_at,
        }
    )

    return Response(
        content='{"ok":true,"status":"issued"}', media_type="application/json"
    )


__all__ = ["router"]
