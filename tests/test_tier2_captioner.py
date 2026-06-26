"""
B3 — Tier-2 captioner against the warm mlx Qwen2.5-VL server on 127.0.0.1:8081.

No real HTTP and no real model: requests is monkeypatched. The DB resume logic
runs against a temp catalog. Verifies the request shape (abs path image_url, no
base64), priority-ordered resume select, idempotent INSERT OR IGNORE + per-image
commit, and that an already-captioned image is skipped.
"""

import types

from pipeline.database import Caption, Image
from pipeline.tier2_captioner import (
    DEFAULT_MODEL,
    Tier2Captioner,
    select_uncaptioned,
)


def _fake_response(payload, ok=True, status=200):
    return types.SimpleNamespace(
        ok=ok,
        status_code=status,
        json=lambda: payload,
        raise_for_status=lambda: None,
    )


def test_health_true_when_status_healthy(monkeypatch):
    import pipeline.tier2_captioner as mod

    monkeypatch.setattr(
        mod.requests,
        "get",
        lambda *a, **k: _fake_response({"status": "healthy"}),
    )
    assert Tier2Captioner().health() is True


def test_health_false_on_connection_error(monkeypatch):
    import pipeline.tier2_captioner as mod

    def boom(*a, **k):
        raise mod.requests.RequestException("down")

    monkeypatch.setattr(mod.requests, "get", boom)
    assert Tier2Captioner().health() is False


def test_caption_image_posts_abs_path_and_returns_text(monkeypatch, tmp_path):
    import pipeline.tier2_captioner as mod

    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _fake_response(
            {"choices": [{"message": {"content": "  a woman standing  "}}]}
        )

    monkeypatch.setattr(mod.requests, "post", fake_post)
    # Resolve to an absolute path we control (the server reads it locally).
    monkeypatch.setattr(mod, "resolve_image_path", lambda p: tmp_path / "x.webp")

    cap = Tier2Captioner()
    text = cap.caption_image("person/x.webp")

    assert text == "a woman standing"  # stripped
    assert captured["url"].endswith("/v1/chat/completions")
    body = captured["json"]
    assert body["model"] == DEFAULT_MODEL
    assert body["max_tokens"] == 160
    assert body["temperature"] == 0.2
    content = body["messages"][0]["content"]
    types_seen = {part["type"] for part in content}
    assert types_seen == {"text", "image_url"}
    img_part = next(p for p in content if p["type"] == "image_url")
    # Absolute path, NOT a base64 data URL.
    assert img_part["image_url"]["url"] == str(tmp_path / "x.webp")
    assert "base64" not in img_part["image_url"]["url"]


def _add_image(session, path, person=None):
    img = Image(path=path, filename=path, person=person, file_hash=path)
    session.add(img)
    session.commit()
    return img.id


def test_select_uncaptioned_skips_captioned_and_priority_orders(db):
    from pipeline.database import Tag

    with db.get_session() as s:
        a = _add_image(s, "a")  # explicit
        b = _add_image(s, "b")  # questionable
        c = _add_image(s, "c")  # general
        # WD rating tags drive priority.
        for img_id, val in [(a, "explicit"), (b, "questionable"), (c, "general")]:
            s.add(
                Tag(
                    image_id=img_id, category="rating", value=val, tag_source="wd_eva02"
                )
            )
        # c already captioned -> excluded.
        s.add(Caption(image_id=c, model=DEFAULT_MODEL, caption="done"))
        s.commit()

    import sqlite3

    conn = sqlite3.connect(db.db_path)
    rows = select_uncaptioned(conn, DEFAULT_MODEL, limit=10)
    conn.close()
    ids = [r[0] for r in rows]
    assert ids == [a, b]  # c excluded; explicit before questionable


def test_select_uncaptioned_rating_filter(db):
    from pipeline.database import Tag

    with db.get_session() as s:
        a = _add_image(s, "a")
        b = _add_image(s, "b")
        for img_id, val in [(a, "explicit"), (b, "general")]:
            s.add(
                Tag(
                    image_id=img_id, category="rating", value=val, tag_source="wd_eva02"
                )
            )
        s.commit()

    import sqlite3

    conn = sqlite3.connect(db.db_path)
    rows = select_uncaptioned(
        conn, DEFAULT_MODEL, limit=10, rating_values=["explicit", "questionable"]
    )
    conn.close()
    assert [r[0] for r in rows] == [a]  # general filtered out


def test_caption_unprocessed_idempotent_commits_per_image(db, monkeypatch):
    with db.get_session() as s:
        _add_image(s, "i1")
        _add_image(s, "i2")

    cap = Tier2Captioner()
    monkeypatch.setattr(cap, "caption_image", lambda rel_path: f"caption of {rel_path}")

    n1 = cap.caption_unprocessed(db, limit=10)
    assert n1 == 2
    with db.get_session() as s:
        assert s.query(Caption).count() == 2

    # Re-run: both already captioned -> no new rows (INSERT OR IGNORE resume).
    n2 = cap.caption_unprocessed(db, limit=10)
    assert n2 == 0
    with db.get_session() as s:
        assert s.query(Caption).count() == 2


def test_caption_unprocessed_does_not_persist_empty_caption(db, monkeypatch):
    """An empty/whitespace caption must NOT be stored (else the image is skipped
    forever); the image stays selectable for a later retry."""
    with db.get_session() as s:
        img_id = _add_image(s, "e1")

    cap = Tier2Captioner()
    monkeypatch.setattr(cap, "caption_image", lambda rel_path: "   ")  # whitespace only

    n = cap.caption_unprocessed(db, limit=10)
    assert n == 0
    with db.get_session() as s:
        assert s.query(Caption).count() == 0

    import sqlite3

    conn = sqlite3.connect(db.db_path)
    still = select_uncaptioned(conn, DEFAULT_MODEL, limit=10)
    conn.close()
    assert [r[0] for r in still] == [img_id]  # still selectable
