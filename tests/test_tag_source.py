"""
A1 (model side) — on a FRESH DB (create_all), the tags UNIQUE key must include
tag_source so WD-EVA02 and JoyTag rows for the same value coexist, while a
re-tag of the same (image, category, value, source) stays idempotent.
"""

from pipeline.database import Tag


def test_add_tags_scored_keeps_both_sources(db, session, sample_image_data):
    img = db.add_image(session, sample_image_data)
    session.commit()
    db.add_tags_scored(
        session,
        img.id,
        [
            {
                "category": "tags",
                "value": "woman",
                "confidence": 0.9,
                "tag_source": "wd_eva02",
            },
            {
                "category": "tags",
                "value": "woman",
                "confidence": 0.8,
                "tag_source": "joytag",
            },
        ],
    )
    rows = session.query(Tag).filter(Tag.image_id == img.id, Tag.value == "woman").all()
    assert sorted(r.tag_source for r in rows) == ["joytag", "wd_eva02"]


def test_add_tags_scored_idempotent_same_source(db, session, sample_image_data):
    """Re-tagging the same (image, category, value, source) yields one row."""
    img = db.add_image(session, sample_image_data)
    session.commit()
    row = {
        "category": "tags",
        "value": "woman",
        "confidence": 0.9,
        "tag_source": "wd_eva02",
    }
    db.add_tags_scored(session, img.id, [row])
    db.add_tags_scored(session, img.id, [row])
    n = session.query(Tag).filter(Tag.image_id == img.id, Tag.value == "woman").count()
    assert n == 1
