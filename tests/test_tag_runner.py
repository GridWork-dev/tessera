"""
B1 + A4 — idempotent, restart-safe fast-tier (Tier-0/3) runner helpers.

`processed=0` is the resume key: the new pipeline sets processed=1 per image
after the requested fast tiers complete, in deterministic id order. Re-tagging
deletes stale model rows first so the 0.45 threshold + tag_source schema apply
cleanly. Rating is derived from the WD rating head via the D2 map.
"""

import sqlite3

import pytest

from pipeline.database import Image, Tag
from pipeline.tag_runner import (
    clear_tier0_tags,
    derive_rating,
    extract_wd_rating,
    finalize_image,
    select_unprocessed_images,
)


def test_extract_wd_rating_finds_rating_row():
    rows = [
        {"category": "tags", "value": "woman", "tag_source": "wd_eva02"},
        {"category": "rating", "value": "explicit", "tag_source": "wd_eva02"},
    ]
    assert extract_wd_rating(rows) == "explicit"


def test_extract_wd_rating_none_when_absent():
    assert extract_wd_rating([{"category": "tags", "value": "x"}]) is None


@pytest.mark.parametrize(
    "wd,expected",
    [
        ("general", "sfw"),
        ("sensitive", "suggestive"),
        ("questionable", "suggestive"),
        ("explicit", "nsfw"),
        ("EXPLICIT", "nsfw"),  # case-insensitive
    ],
)
def test_derive_rating_d2_map(wd, expected):
    assert derive_rating(wd) == expected


def test_derive_rating_unknown_is_unrated():
    assert derive_rating("banana") == "unrated"
    assert derive_rating(None) == "unrated"


def _add_image(db, session, path, processed=False, person=None):
    img = Image(
        path=path, filename=path, person=person, file_hash=path, processed=processed
    )
    session.add(img)
    session.commit()
    return img.id


def test_select_unprocessed_skips_processed_in_id_order(db):
    with db.get_session() as s:
        a = _add_image(db, s, "a", processed=True)
        b = _add_image(db, s, "b", processed=False)
        c = _add_image(db, s, "c", processed=False)
    conn = sqlite3.connect(db.db_path)
    rows = select_unprocessed_images(conn, count=10)
    conn.close()
    ids = [r[0] for r in rows]
    assert ids == [b, c]
    assert a not in ids


def test_select_unprocessed_respects_count_and_person(db):
    with db.get_session() as s:
        _add_image(db, s, "p1", processed=False, person="Alice")
        _add_image(db, s, "p2", processed=False, person="Alice")
        _add_image(db, s, "p3", processed=False, person="Bob")
    conn = sqlite3.connect(db.db_path)
    alice = select_unprocessed_images(conn, count=10, person="Alice")
    limited = select_unprocessed_images(conn, count=1)
    conn.close()
    assert {r[1] for r in alice} == {"p1", "p2"}
    assert len(limited) == 1


def test_clear_tier0_tags_removes_only_model_rows(db, session, sample_image_data):
    img = db.add_image(session, sample_image_data)
    session.commit()
    db.add_tags_scored(
        session,
        img.id,
        [
            {
                "category": "tags",
                "value": "a",
                "confidence": 0.9,
                "tag_source": "wd_eva02",
            },
            {
                "category": "tags",
                "value": "b",
                "confidence": 0.9,
                "tag_source": "joytag",
            },
            {"category": "tags", "value": "c", "confidence": 1.0, "tag_source": "user"},
        ],
    )
    clear_tier0_tags(session, img.id)
    session.commit()
    remaining = {
        (t.value, t.tag_source)
        for t in session.query(Tag).filter(Tag.image_id == img.id).all()
    }
    assert remaining == {("c", "user")}


def test_finalize_image_sets_processed_and_rating(db, session, sample_image_data):
    from tests.conftest import add_label_tables
    from webui.search import rating_map_for_ids

    img = db.add_image(session, sample_image_data)
    session.commit()
    add_label_tables(db)  # Rating label set + user_labels (Wave 2c)
    finalize_image(session, img.id, "explicit")
    session.commit()
    row = session.get(Image, img.id)
    assert row.processed is True
    # Rating is now a Rating LABEL assignment, not a column.
    assert rating_map_for_ids(session, [img.id]) == {img.id: "nsfw"}


def test_finalize_image_without_rating_leaves_rating_unchanged(
    db, session, sample_image_data
):
    from tests.conftest import add_label_tables
    from webui.search import rating_map_for_ids

    img = db.add_image(session, sample_image_data)
    session.commit()
    add_label_tables(db)
    finalize_image(session, img.id, None)
    session.commit()
    row = session.get(Image, img.id)
    assert row.processed is True
    # No rating value passed -> no Rating label written (unrated == absence).
    assert rating_map_for_ids(session, [img.id]) == {}
