"""Unit tests for pipeline.auth — password hashing, tokens, and the enable gate.

No torch / no network / no model weights; pure stdlib crypto primitives.
"""

import pytest

from pipeline import auth


# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #
def test_hash_and_verify_roundtrip():
    h = auth.hash_password("correct horse battery staple")
    assert h and "$" in h
    assert auth.verify_password("correct horse battery staple", h)
    assert not auth.verify_password("wrong", h)


def test_hash_is_salted_unique():
    a = auth.hash_password("samepw")
    b = auth.hash_password("samepw")
    assert a != b  # random salt per hash
    assert auth.verify_password("samepw", a)
    assert auth.verify_password("samepw", b)


def test_empty_password_rejected():
    with pytest.raises(ValueError):
        auth.hash_password("")


def test_verify_against_garbage_is_false():
    assert not auth.verify_password("x", "")
    assert not auth.verify_password("x", "not-a-valid-hash")
    assert not auth.verify_password("x", "unknownalgo$abc")


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #
def test_token_roundtrip(monkeypatch):
    monkeypatch.setenv("MEDIA_PIPELINE_AUTH_SECRET", "unit-secret")
    tok = auth.issue_token(7, "alice", "admin")
    p = auth.verify_token(tok)
    assert p is not None
    assert (p.user_id, p.username, p.role) == (7, "alice", "admin")
    assert p.is_admin


def test_tampered_token_rejected(monkeypatch):
    monkeypatch.setenv("MEDIA_PIPELINE_AUTH_SECRET", "unit-secret")
    tok = auth.issue_token(1, "bob", "user")
    assert auth.verify_token(tok[:-3] + "AAA") is None
    assert auth.verify_token("garbage") is None
    assert auth.verify_token("") is None


def test_token_wrong_secret_rejected(monkeypatch):
    monkeypatch.setenv("MEDIA_PIPELINE_AUTH_SECRET", "secret-one")
    tok = auth.issue_token(1, "bob", "user")
    monkeypatch.setenv("MEDIA_PIPELINE_AUTH_SECRET", "secret-two")
    assert auth.verify_token(tok) is None


def test_expired_token_rejected(monkeypatch):
    monkeypatch.setenv("MEDIA_PIPELINE_AUTH_SECRET", "unit-secret")
    tok = auth.issue_token(1, "bob", "user", ttl=-1)
    assert auth.verify_token(tok) is None


def test_extract_bearer():
    assert auth.extract_bearer("Bearer abc.def") == "abc.def"
    assert auth.extract_bearer("bearer xyz") == "xyz"
    assert auth.extract_bearer("Basic abc") is None
    assert auth.extract_bearer(None) is None


# --------------------------------------------------------------------------- #
# Enable gate — OFF by default, ON when configured
# --------------------------------------------------------------------------- #
def test_gate_off_by_default(monkeypatch):
    for k in (
        "MEDIA_PIPELINE_AUTH_ENABLED",
        "MEDIA_PIPELINE_ADMIN_PASSWORD",
    ):
        monkeypatch.delenv(k, raising=False)
    assert auth.auth_enabled("127.0.0.1") is False
    assert auth.auth_enabled(None) is False


def test_gate_on_with_admin_password(monkeypatch):
    monkeypatch.delenv("MEDIA_PIPELINE_AUTH_ENABLED", raising=False)
    monkeypatch.setenv("MEDIA_PIPELINE_ADMIN_PASSWORD", "pw")
    assert auth.auth_enabled("127.0.0.1") is True


def test_gate_on_with_nonlocal_bind(monkeypatch):
    monkeypatch.delenv("MEDIA_PIPELINE_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("MEDIA_PIPELINE_ADMIN_PASSWORD", raising=False)
    assert auth.auth_enabled("0.0.0.0") is True
    assert auth.auth_enabled("192.168.1.5") is True
    assert auth.auth_enabled("localhost") is False


def test_gate_explicit_override_wins(monkeypatch):
    monkeypatch.setenv("MEDIA_PIPELINE_ADMIN_PASSWORD", "pw")
    monkeypatch.setenv("MEDIA_PIPELINE_AUTH_ENABLED", "0")
    assert auth.auth_enabled("0.0.0.0") is False
    monkeypatch.setenv("MEDIA_PIPELINE_AUTH_ENABLED", "1")
    monkeypatch.delenv("MEDIA_PIPELINE_ADMIN_PASSWORD", raising=False)
    assert auth.auth_enabled("127.0.0.1") is True
