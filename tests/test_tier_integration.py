"""Integration tests for the tier-tagger DB writer (Database.add_tags_scored).

Asserts the new scored writer persists per-row ``tag_source`` + ``confidence``
(which the legacy ``add_tags`` does NOT) and is idempotent under re-run. Uses the
conftest temp-db fixtures — never the real catalog.db.
"""

from pipeline.database import Tag


def _seed_image(db, session):
    """Insert a minimal image row and return its id."""
    img = db.add_image(
        session,
        {
            "path": "library/test/sfw/abc123def456.webp",
            "filename": "abc123def456.webp",
            "directory": "library/test/sfw",
            "person": "test",
            "file_hash": "abc123def456",
            "width": 100,
            "height": 100,
            "filesize": 1234,
            "format": "webp",
            "created_at": None,
            "modified_at": None,
        },
    )
    session.commit()
    return img.id


def test_add_tags_scored_sets_source_and_confidence(db, session):
    image_id = _seed_image(db, session)
    rows = [
        {
            "category": "tags",
            "value": "1girl",
            "confidence": 0.97,
            "tag_source": "wd_eva02",
        },
        {
            "category": "rating",
            "value": "general",
            "confidence": 0.88,
            "tag_source": "wd_eva02",
        },
        {
            "category": "tags",
            "value": "solo",
            "confidence": 0.71,
            "tag_source": "joytag",
        },
        {
            "category": "person",
            "value": "alice",
            "confidence": 0.91,
            "tag_source": "wd_eva02",
        },
    ]
    db.add_tags_scored(session, image_id, rows)

    tags = session.query(Tag).filter(Tag.image_id == image_id).all()
    assert len(tags) == 4

    by_val = {t.value: t for t in tags}
    assert by_val["1girl"].tag_source == "wd_eva02"
    assert by_val["1girl"].category == "tags"
    assert abs(by_val["1girl"].confidence - 0.97) < 1e-6

    assert by_val["solo"].tag_source == "joytag"
    assert abs(by_val["solo"].confidence - 0.71) < 1e-6

    assert by_val["general"].category == "rating"
    assert by_val["alice"].category == "person"
    assert by_val["alice"].tag_source == "wd_eva02"


def test_add_tags_scored_is_idempotent(db, session):
    image_id = _seed_image(db, session)
    rows = [
        {
            "category": "tags",
            "value": "1girl",
            "confidence": 0.97,
            "tag_source": "wd_eva02",
        },
        {
            "category": "tags",
            "value": "solo",
            "confidence": 0.71,
            "tag_source": "joytag",
        },
    ]
    db.add_tags_scored(session, image_id, rows)
    # Second call with the same (image_id, category, value) keys -> no duplicates.
    db.add_tags_scored(session, image_id, rows)

    tags = session.query(Tag).filter(Tag.image_id == image_id).all()
    assert len(tags) == 2

    # The original row wins on conflict (on_conflict_do_nothing), not overwritten.
    by_val = {t.value: t for t in tags}
    assert by_val["1girl"].tag_source == "wd_eva02"
    assert by_val["solo"].tag_source == "joytag"


def test_add_tags_scored_does_not_touch_rating_label(db, session):
    """The scored writer only writes Tag rows; the Rating LABEL set is untouched.

    Rating is a label set now (Wave 2c — images.rating column dropped): writing a
    machine ``rating`` TAG must not assign a human Rating label.
    """
    from tests.conftest import add_label_tables
    from webui.search import rating_map_for_ids

    image_id = _seed_image(db, session)
    session.commit()
    add_label_tables(db)
    db.add_tags_scored(
        session,
        image_id,
        [
            {
                "category": "rating",
                "value": "explicit",
                "confidence": 0.6,
                "tag_source": "wd_eva02",
            }
        ],
    )
    session.commit()
    assert rating_map_for_ids(session, [image_id]) == {}
