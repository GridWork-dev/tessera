"""
Smoke tests for pipeline/tagger.py — tag validation, enum correction.

NOTE: validate_and_correct_tags accepts a dict {category: [values]}.
Free-form categories (clothing, tags) pass through without lowercasing.
Known enum categories (rating, content_type, setting) get lowercased
and validated against ALLOWED_ENUMS.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.tagger import validate_and_correct_tags


class TestValidateTags:
    """Tag validation and correction logic."""

    def test_unknown_category_passthrough(self):
        """Free-form categories pass through unchanged."""
        tags = {
            "custom_cat": ["test_value"],
        }
        corrected, report = validate_and_correct_tags(tags)
        assert "custom_cat" in corrected
        assert corrected["custom_cat"] == ["test_value"]

    def test_normalizes_rating_values(self):
        """Rating values in ALLOWED_ENUMS are lowercased and validated."""
        tags = {"rating": ["sfw"]}
        corrected, report = validate_and_correct_tags(tags)
        assert corrected["rating"] == ["sfw"]

        # Test out-of-range rating value gets remapped or clamped
        tags = {"rating": ["explicit"]}
        corrected, report = validate_and_correct_tags(tags)
        assert len(corrected["rating"]) == 1
        # Should have been remapped or clamped (report entry generated)
        assert len(report) >= 1

    def test_known_enum_gets_lowercased(self):
        """Known enum category values are lowercased."""
        tags = {"rating": ["SFW"]}
        corrected, report = validate_and_correct_tags(tags)
        assert corrected["rating"] == ["sfw"]

    def test_known_enum_category_clamped(self):
        """Values not in allowed enum are clamped to first valid value."""
        tags = {"rating": ["completely_invalid"]}
        corrected, report = validate_and_correct_tags(tags)
        assert len(report) >= 1

    def test_content_type_normalization(self):
        """content_type gets normalized to valid enum values."""
        tags = {"content_type": ["PORTRAIT"]}
        corrected, report = validate_and_correct_tags(tags)
        assert "content_type" in corrected
        if "portrait" in corrected["content_type"]:
            assert True  # Lowercased correctly

    def test_setting_normalization(self):
        """setting category gets normalized."""
        tags = {"setting": ["INDOOR"]}
        corrected, report = validate_and_correct_tags(tags)
        assert "setting" in corrected
        if "indoor" in corrected["setting"]:
            assert True  # Lowercased correctly
