"""In-app License panel API tests (Spec J) — GET/POST/DELETE /api/license.

Exercises the real webui.main app via TestClient. An ephemeral Ed25519 keypair is
generated and the app's baked-in public key is monkeypatched to it (per
tests/test_licensing_crypto.py), so we sign valid test tokens without the prod
private key. ``project_root`` is redirected to ``tmp_path`` via env so license.key
is written/removed in a temp dir and never touches the real project root.

Fully offline: no network, no torch, no real catalog.db.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("cryptography")

from pipeline import license_tokens as lt  # noqa: E402
from pipeline import licensing  # noqa: E402
from pipeline.database import Database  # noqa: E402
from pipeline.license_tokens import (  # noqa: E402
    LicenseClaims,
    generate_keypair,
    load_private_key_b64,
    sign_token,
)
from pipeline.settings import REPO_ROOT, reload_settings  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Real app with project_root -> tmp_path and an ephemeral verification key."""
    # Ephemeral keypair; point the app's verifier at the ephemeral public key.
    priv_b64, pub_b64 = generate_keypair()
    monkeypatch.setattr(lt, "PUBLIC_KEY_B64", pub_b64)

    # A throwaway catalog.db so importing webui.main doesn't touch the real one.
    db = tmp_path / "catalog.db"
    Database(str(db))

    monkeypatch.delenv("MEDIA_PIPELINE_LICENSE", raising=False)
    monkeypatch.setenv("MEDIA_PIPELINE_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("MEDIA_PIPELINE_DATABASE_PATH", str(db))
    # Rebind the module-level settings singleton so webui.main (which does
    # ``from pipeline.settings import settings`` at import) binds its db to the
    # temp catalog — reload_settings() alone only clears the lru_cache.
    import pipeline.settings as _ps

    monkeypatch.setattr(_ps, "settings", reload_settings())

    import webui.main

    try:
        yield TestClient(webui.main.app), load_private_key_b64(priv_b64), tmp_path
    finally:
        reload_settings()


def _pro_token(private_key, *, max_version=None, customer_id="cust_test"):
    mv = max_version if max_version is not None else licensing.APP_MAJOR_VERSION
    claims = LicenseClaims(
        tier="pro",
        max_version=mv,
        issued_at=int(time.time()),
        customer_id=customer_id,
    )
    return sign_token(claims, private_key)


def test_get_license_defaults_to_community(client):
    api, _private_key, _root = client
    r = api.get("/api/license")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tier"] == "community"
    assert body["features"] == {
        "bulk_export": False,
        "remote_compute_routing": False,
        "priority_support": False,
    }
    assert body["max_version"] is None
    assert isinstance(body["detail"], str)


def test_post_valid_token_unlocks_pro_and_persists(client):
    api, private_key, root = client
    token = _pro_token(private_key)

    r = api.post("/api/license", json={"token": token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["tier"] == "pro"

    # license.key written to the (temp) project root — not the real repo root.
    key_file = Path(root) / "license.key"
    assert key_file.is_file()
    assert key_file.read_text(encoding="utf-8").strip() == token

    # GET now reports pro with all three features + the signed max_version.
    g = api.get("/api/license").json()
    assert g["tier"] == "pro"
    assert g["features"] == {
        "bulk_export": True,
        "remote_compute_routing": True,
        "priority_support": True,
    }
    assert g["max_version"] == licensing.APP_MAJOR_VERSION


def test_delete_reverts_to_community(client):
    api, private_key, root = client
    api.post("/api/license", json={"token": _pro_token(private_key)})
    assert (Path(root) / "license.key").is_file()

    d = api.delete("/api/license")
    assert d.status_code == 200, d.text
    assert d.json() == {"ok": True, "tier": "community"}
    assert not (Path(root) / "license.key").exists()

    assert api.get("/api/license").json()["tier"] == "community"


def test_delete_when_absent_never_errors(client):
    api, _private_key, root = client
    assert not (Path(root) / "license.key").exists()
    d = api.delete("/api/license")
    assert d.status_code == 200
    assert d.json()["tier"] == "community"


@pytest.mark.parametrize("bad", ["", "garbage", "MPL-PRO-not_base64!!"])
def test_post_forged_or_garbage_token_400_writes_nothing(client, bad):
    api, _private_key, root = client
    r = api.post("/api/license", json={"token": bad})
    assert r.status_code == 400, r.text
    assert not (Path(root) / "license.key").exists()
    # Still community after a rejected save.
    assert api.get("/api/license").json()["tier"] == "community"


def test_post_token_signed_by_wrong_key_rejected(client):
    api, _private_key, root = client
    # A token signed by a DIFFERENT key fails against the baked-in (ephemeral) key.
    attacker_priv_b64, _ = generate_keypair()
    forged = _pro_token(load_private_key_b64(attacker_priv_b64))

    r = api.post("/api/license", json={"token": forged})
    assert r.status_code == 400
    assert not (Path(root) / "license.key").exists()


def test_real_project_root_untouched(client):
    """Sanity: the redirect means we never write license.key into the real repo."""
    api, private_key, _root = client
    api.post("/api/license", json={"token": _pro_token(private_key)})
    assert not (REPO_ROOT / "license.key").exists()
