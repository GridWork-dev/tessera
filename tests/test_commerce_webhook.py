"""Polar order.paid webhook tests (Spec J, issuer-only).

Self-gating: unset secret -> 503. With a secret, a correctly Standard-Webhooks-
signed ``order.paid`` mints exactly ONE Ed25519 token (verified against the test
public key), appends one line to a TEMP ledger, and a retried delivery of the same
order_id re-uses the token (ledger stays at one line). A wrong-signature payload is
401 with no mint, no ledger write.

No prod private key: an ephemeral keypair is generated; the signing key is fed via
``MEDIA_PIPELINE_LICENSE_PRIVATE_KEY`` and the app's verifier is monkeypatched to
the ephemeral public key. The ledger path is redirected via project_root ->
tmp_path. Fully offline.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("cryptography")

from pipeline import license_tokens as lt  # noqa: E402
from pipeline.database import Database  # noqa: E402
from pipeline.license_tokens import generate_keypair, verify_token  # noqa: E402
from pipeline.settings import reload_settings  # noqa: E402

SECRET_PLAIN = "supersecretwebhookkey"
# Standard-Webhooks / Polar secrets are ``whsec_<base64>``; the HMAC key is the
# base64-decoded part after the prefix.
SECRET = "whsec_" + base64.b64encode(SECRET_PLAIN.encode()).decode()
SECRET_KEY_BYTES = SECRET_PLAIN.encode()


def _sign(
    body: bytes, *, webhook_id="msg_1", timestamp=None, secret_key=SECRET_KEY_BYTES
):
    ts = timestamp or str(int(time.time()))
    signed = webhook_id.encode() + b"." + ts.encode() + b"." + body
    sig = base64.b64encode(
        hmac.new(secret_key, signed, hashlib.sha256).digest()
    ).decode()
    return {
        "webhook-id": webhook_id,
        "webhook-timestamp": ts,
        "webhook-signature": f"v1,{sig}",
    }


def _order_paid_payload(order_id="order_abc", major_version=1):
    return {
        "type": "order.paid",
        "data": {
            "id": order_id,
            "customer_id": "cust_99",
            "customer": {"email": "buyer@example.com"},
            "product": {"metadata": {"major_version": major_version}},
        },
    }


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    """Factory: build a TestClient with/without the webhook secret configured.

    Returns ``(build, pub_b64, tmp_path)`` where ``build(secret=...)`` yields a
    fresh TestClient under the requested config. project_root -> tmp_path so the
    ledger lands in a temp dir.
    """
    priv_b64, pub_b64 = generate_keypair()
    monkeypatch.setattr(lt, "PUBLIC_KEY_B64", pub_b64)

    db = tmp_path / "catalog.db"
    Database(str(db))
    monkeypatch.setenv("MEDIA_PIPELINE_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("MEDIA_PIPELINE_DATABASE_PATH", str(db))
    monkeypatch.delenv("MEDIA_PIPELINE_LICENSE", raising=False)
    # The issuer signing key (ephemeral test key) — env only.
    monkeypatch.setenv("MEDIA_PIPELINE_LICENSE_PRIVATE_KEY", priv_b64)

    def build(secret: str | None):
        if secret is None:
            monkeypatch.delenv("MEDIA_PIPELINE_POLAR_WEBHOOK_SECRET", raising=False)
        else:
            monkeypatch.setenv("MEDIA_PIPELINE_POLAR_WEBHOOK_SECRET", secret)
        # Rebind the settings singleton so webui.main binds its db to the temp
        # catalog on first import (the commerce routes themselves read settings
        # fresh via get_settings(), but the module-level import must not crash).
        import pipeline.settings as _ps

        monkeypatch.setattr(_ps, "settings", reload_settings())
        import webui.main

        return TestClient(webui.main.app)

    try:
        yield build, pub_b64, tmp_path
    finally:
        reload_settings()


def _ledger_path(root: Path) -> Path:
    return Path(root) / "outputs" / "licenses" / "ledger.jsonl"


def _ledger_lines(root: Path) -> list[dict]:
    path = _ledger_path(root)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_unconfigured_secret_returns_503(make_client):
    build, _pub, _root = make_client
    api = build(secret=None)
    body = json.dumps(_order_paid_payload()).encode()
    r = api.post("/api/commerce/webhook/polar", content=body, headers=_sign(body))
    assert r.status_code == 503, r.text


def test_valid_order_paid_mints_one_token(make_client):
    build, pub_b64, root = make_client
    api = build(secret=SECRET)

    body = json.dumps(
        _order_paid_payload(order_id="order_one", major_version=2)
    ).encode()
    r = api.post("/api/commerce/webhook/polar", content=body, headers=_sign(body))
    assert r.status_code == 200, r.text
    # The token is NOT returned in the response body.
    assert "MPL-" not in r.text

    lines = _ledger_lines(root)
    assert len(lines) == 1
    entry = lines[0]
    assert entry["order_id"] == "order_one"
    assert entry["customer_id"] == "cust_99"
    assert entry["email"] == "buyer@example.com"
    assert entry["major_version"] == 2

    # The minted token verifies against the ephemeral public key as a pro token.
    claims = verify_token(entry["token"], public_key_b64=pub_b64)
    assert claims is not None
    assert claims.tier == "pro"
    assert claims.max_version == 2
    assert claims.customer_id == "cust_99"
    assert claims.expires is None  # perpetual-per-major


def test_retry_same_order_reuses_token(make_client):
    build, _pub, root = make_client
    api = build(secret=SECRET)

    payload = _order_paid_payload(order_id="order_retry")
    body = json.dumps(payload).encode()

    r1 = api.post("/api/commerce/webhook/polar", content=body, headers=_sign(body))
    assert r1.status_code == 200, r1.text
    first = _ledger_lines(root)
    assert len(first) == 1
    token1 = first[0]["token"]

    # A retried delivery (new webhook-id, same order_id) must NOT mint again.
    r2 = api.post(
        "/api/commerce/webhook/polar",
        content=body,
        headers=_sign(body, webhook_id="msg_2"),
    )
    assert r2.status_code == 200, r2.text
    second = _ledger_lines(root)
    assert len(second) == 1  # still one line
    assert second[0]["token"] == token1  # same token re-used


def test_wrong_signature_401_no_mint(make_client):
    build, _pub, root = make_client
    api = build(secret=SECRET)

    body = json.dumps(_order_paid_payload(order_id="order_forged")).encode()
    # Sign with a DIFFERENT key -> signature mismatch.
    bad_headers = _sign(body, secret_key=b"the-wrong-key")
    r = api.post("/api/commerce/webhook/polar", content=body, headers=bad_headers)
    assert r.status_code == 401, r.text
    assert _ledger_lines(root) == []  # nothing minted, nothing written


def test_missing_signature_headers_401(make_client):
    build, _pub, root = make_client
    api = build(secret=SECRET)
    body = json.dumps(_order_paid_payload()).encode()
    r = api.post(
        "/api/commerce/webhook/polar",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 401
    assert _ledger_lines(root) == []


def test_non_order_paid_event_acked_no_mint(make_client):
    build, _pub, root = make_client
    api = build(secret=SECRET)
    payload = {"type": "checkout.created", "data": {"id": "co_1"}}
    body = json.dumps(payload).encode()
    r = api.post("/api/commerce/webhook/polar", content=body, headers=_sign(body))
    assert r.status_code == 200, r.text
    assert _ledger_lines(root) == []  # ignored event -> no mint
