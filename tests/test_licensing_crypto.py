"""Ed25519 license-token tests — real signature verification (Spec I, §5).

Generates an EPHEMERAL keypair per test session, monkeypatches the app's baked-in
public key to the ephemeral public, and exercises the sign->verify round-trip plus
every fail-safe path (tamper, over-version, expired, forged, community fallback).

No network, no torch, no model load, no real catalog.db. ``cryptography`` is the
only non-stdlib dep and is part of the core stack; guard import defensively to
mirror tests/test_self_retrieval.py's skip discipline.
"""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

cryptography = pytest.importorskip("cryptography")

from pipeline import license_tokens as lt  # noqa: E402
from pipeline import licensing  # noqa: E402
from pipeline.license_tokens import (  # noqa: E402
    LicenseClaims,
    generate_keypair,
    load_private_key_b64,
    sign_token,
    verify_token,
)
from pipeline.licensing import (  # noqa: E402
    ProFeature,
    Tier,
    feature_enabled,
    load_license,
    parse_token,
    verify_pro,
)


@pytest.fixture
def keypair(monkeypatch):
    """Ephemeral Ed25519 keypair; baked-in public key swapped to the ephemeral."""
    priv_b64, pub_b64 = generate_keypair()
    # Point the app's verifier at the ephemeral public key.
    monkeypatch.setattr(lt, "PUBLIC_KEY_B64", pub_b64)
    return load_private_key_b64(priv_b64), priv_b64, pub_b64


def _pro_token(private_key, *, max_version=1, expires=None, customer_id=None):
    claims = LicenseClaims(
        tier="pro",
        max_version=max_version,
        issued_at=int(time.time()),
        customer_id=customer_id,
        expires=expires,
    )
    return sign_token(claims, private_key)


# --------------------------------------------------------------------------- #
# Round-trip: a properly-signed pro token verifies and unlocks features.       #
# --------------------------------------------------------------------------- #
def test_round_trip_sign_verify(keypair, monkeypatch):
    private_key, _, _ = keypair
    monkeypatch.delenv("MEDIA_PIPELINE_LICENSE", raising=False)
    token = _pro_token(private_key, max_version=1, customer_id="cust_42")

    claims = verify_token(token)
    assert claims is not None
    assert claims.tier == "pro"
    assert claims.max_version == 1
    assert claims.customer_id == "cust_42"

    assert verify_pro(token) is True
    assert parse_token(token) is Tier.PRO


def test_round_trip_unlocks_pro_features(keypair, monkeypatch, tmp_path):
    private_key, _, _ = keypair
    token = _pro_token(private_key, max_version=licensing.APP_MAJOR_VERSION)
    monkeypatch.setenv("MEDIA_PIPELINE_LICENSE", token)

    st = load_license(project_root=tmp_path)
    assert st.tier is Tier.PRO
    assert st.has(ProFeature.REMOTE_COMPUTE_ROUTING)
    assert feature_enabled(ProFeature.BULK_EXPORT, status=st)


def test_pro_token_via_key_file(keypair, monkeypatch, tmp_path):
    private_key, _, _ = keypair
    monkeypatch.delenv("MEDIA_PIPELINE_LICENSE", raising=False)
    token = _pro_token(private_key, max_version=licensing.APP_MAJOR_VERSION)
    (tmp_path / "license.key").write_text(token + "\n", encoding="utf-8")

    st = load_license(project_root=tmp_path)
    assert st.tier is Tier.PRO


# --------------------------------------------------------------------------- #
# Tamper detection: any mutation of the signed blob invalidates the signature. #
# --------------------------------------------------------------------------- #
def test_tampered_payload_rejected(keypair):
    private_key, _, _ = keypair
    token = _pro_token(private_key, max_version=1)
    prefix, tier_seg, opaque = token.split("-", 2)
    # Flip one base64 char in the opaque segment.
    flipped = ("A" if opaque[0] != "A" else "B") + opaque[1:]
    tampered = f"{prefix}-{tier_seg}-{flipped}"

    assert verify_token(tampered) is None
    assert parse_token(tampered) is Tier.COMMUNITY


def test_forged_prefix_cannot_grant(keypair):
    """A token signed as community cannot be promoted by editing the visible prefix."""
    private_key, _, _ = keypair
    claims = LicenseClaims(tier="community", max_version=99, issued_at=int(time.time()))
    community_token = sign_token(claims, private_key)
    # Attacker rewrites the human-readable tier segment to PRO.
    prefix, _seg, opaque = community_token.split("-", 2)
    forged = f"{prefix}-PRO-{opaque}"

    # Signature still valid, but the SIGNED tier is community -> no Pro.
    assert verify_pro(forged) is False
    assert parse_token(forged) is Tier.COMMUNITY


def test_wrong_key_rejected(monkeypatch):
    """A token signed by a different key fails against the baked-in public key."""
    attacker_priv_b64, _ = generate_keypair()
    _victim_priv_b64, victim_pub_b64 = generate_keypair()
    monkeypatch.setattr(lt, "PUBLIC_KEY_B64", victim_pub_b64)

    token = _pro_token(load_private_key_b64(attacker_priv_b64), max_version=1)
    assert verify_token(token) is None
    assert parse_token(token) is Tier.COMMUNITY


# --------------------------------------------------------------------------- #
# Perpetual-per-major: max_version below the app major -> community.           #
# --------------------------------------------------------------------------- #
def test_over_version_downgrades_to_community(keypair, monkeypatch):
    private_key, _, _ = keypair
    # App is "v2" but the token only covers up to v1.
    monkeypatch.setattr(licensing, "APP_MAJOR_VERSION", 2)
    token = _pro_token(private_key, max_version=1)

    # Signature verifies (claims returned) but the version rule fails safe.
    assert verify_token(token) is not None
    assert verify_pro(token) is False
    assert parse_token(token) is Tier.COMMUNITY


def test_future_major_token_grants_current(keypair, monkeypatch):
    """A token covering a higher major still grants Pro on the current major."""
    private_key, _, _ = keypair
    monkeypatch.setattr(licensing, "APP_MAJOR_VERSION", 1)
    token = _pro_token(private_key, max_version=3)
    assert verify_pro(token) is True


# --------------------------------------------------------------------------- #
# Expiry: an expired token fails safe to community (perpetual fallback handled  #
# by max_version, not by exp).                                                 #
# --------------------------------------------------------------------------- #
def test_expired_token_rejected(keypair):
    private_key, _, _ = keypair
    token = _pro_token(private_key, max_version=1, expires=int(time.time()) - 10)
    assert verify_token(token) is None
    assert parse_token(token) is Tier.COMMUNITY


def test_unexpired_token_accepted(keypair):
    private_key, _, _ = keypair
    token = _pro_token(private_key, max_version=1, expires=int(time.time()) + 3600)
    assert verify_pro(token) is True


# --------------------------------------------------------------------------- #
# Community fallback: missing / empty / malformed -> community, never raises.  #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "bad",
    [None, "", "garbage", "MPL-PRO", "MPL-PRO-", "XXX-PRO-abc", "MPL-PRO-not_base64!!"],
)
def test_malformed_tokens_fail_safe(bad):
    assert verify_token(bad) is None
    assert verify_pro(bad) is False
    assert parse_token(bad) is Tier.COMMUNITY


def test_no_token_is_community(monkeypatch, tmp_path):
    monkeypatch.delenv("MEDIA_PIPELINE_LICENSE", raising=False)
    st = load_license(project_root=tmp_path)
    assert st.tier is Tier.COMMUNITY
    assert not st.has(ProFeature.BULK_EXPORT)


def test_community_pro_feature_gated():
    from pipeline.licensing import LicenseStatus

    community = LicenseStatus()
    assert not feature_enabled(ProFeature.PRIORITY_SUPPORT, status=community)


# --------------------------------------------------------------------------- #
# Issuing tool: produces a token the app accepts end-to-end.                   #
# --------------------------------------------------------------------------- #
def test_issue_license_cli_round_trip(keypair, monkeypatch, capsys):
    _private_key, priv_b64, _pub_b64 = keypair
    issue = importlib.import_module("scripts.issue_license")
    monkeypatch.setenv(issue.PRIVATE_KEY_ENV, priv_b64)

    rc = issue.main(
        ["--tier", "pro", "--max-version", str(licensing.APP_MAJOR_VERSION)]
    )
    assert rc == 0
    token = capsys.readouterr().out.strip()
    assert token.startswith("MPL-PRO-")
    assert parse_token(token) is Tier.PRO


def test_issue_license_cli_gen_key(monkeypatch, capsys):
    issue = importlib.import_module("scripts.issue_license")
    rc = issue.main(["--gen-key"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "PRIVATE" in out and "PUBLIC" in out
