"""
Tests for Tier 3 NudeNet region detection.

Covers the pure ``convert_regions`` mapping and ``write_regions`` persistence.
The real NudeNet model is never loaded — the detector is mocked.
"""

import json
from unittest.mock import MagicMock

from pipeline.database import Image
from pipeline.tier3_nudenet import Tier3NudeNet, convert_regions


def test_convert_regions_box_xywh_to_xyxy():
    """[x, y, w, h] -> [x1, y1, x2, y2] with label/score preserved."""
    raw = [{"class": "FACE_FEMALE", "score": 0.91, "box": [10, 20, 30, 40]}]
    out = convert_regions(raw)
    assert out == [{"label": "FACE_FEMALE", "score": 0.91, "box": [10, 20, 40, 60]}]


def test_convert_regions_rounds_score():
    raw = [{"class": "X", "score": 0.123456, "box": [0, 0, 1, 1]}]
    assert convert_regions(raw)[0]["score"] == 0.1235


def test_convert_regions_empty():
    """Empty detections -> empty list."""
    assert convert_regions([]) == []


def test_detect_image_uses_mocked_detector():
    """detect_image runs convert_regions over the (mocked) detector output."""
    tier = Tier3NudeNet()
    tier._detector = MagicMock()
    tier._detector.detect.return_value = [
        {"class": "FACE_FEMALE", "score": 0.5, "box": [1, 2, 3, 4]}
    ]
    out = tier.detect_image("test_person/test_image.jpg")
    assert out == [{"label": "FACE_FEMALE", "score": 0.5, "box": [1, 2, 4, 6]}]


def test_write_regions_roundtrip_and_rating_unchanged(db, sample_image_data):
    """write_regions persists JSON, sets nudenet_checked, never touches rating.

    Rating is the Rating LABEL set now (Wave 2c — images.rating column dropped);
    NudeNet is metadata and must never assign a Rating label.
    """
    from tests.conftest import add_label_tables
    from webui.search import rating_map_for_ids

    with db.get_session() as session:
        image = db.add_image(session, sample_image_data)
        session.commit()
        image_id = image.id
    add_label_tables(db)

    regions = [{"label": "FACE_FEMALE", "score": 0.91, "box": [10, 20, 40, 60]}]
    tier = Tier3NudeNet()

    with db.get_session() as session:
        tier.write_regions(session, image_id, regions)

    with db.get_session() as session:
        row = session.query(Image).filter(Image.id == image_id).one()
        assert json.loads(row.nudenet_regions) == regions
        assert row.nudenet_checked == 1
        # NudeNet never gates rating: no Rating label was written.
        assert rating_map_for_ids(session, [image_id]) == {}
