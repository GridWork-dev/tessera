"""Tag enum schema + validation/correction for VLM tagger output.

Extracted from ``pipeline.tagger`` (pure mechanical move — no behavior change).
``pipeline.tagger`` re-exports ``ALLOWED_ENUMS``, ``REMAP`` and
``validate_and_correct_tags``, so existing imports such as
``from pipeline.tagger import validate_and_correct_tags`` keep working unchanged.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── Enum Schema Validation ──

# Allowed values per tag category. Any value outside these enums is auto-corrected.
ALLOWED_ENUMS = {
    "rating": ["sfw", "suggestive", "nsfw"],
    "content_type": [
        "portrait",
        "full_body",
        "closeup",
        "landscape",
        "selfie",
        "group",
        "action",
        "headshot",
        "bust",
        "half_body",
        "three_quarter",
        "bodyscape",
    ],
    "pose": [
        "standing",
        "sitting",
        "reclining",
        "kneeling",
        "leaning",
        "laying",
        "crouching",
        "bending",
        "walking",
        "posing",
    ],
    "composition": [
        "headshot",
        "half_body",
        "three_quarter",
        "full_body",
        "wide",
        "closeup_detail",
        "dutch_angle",
    ],
    "setting": [
        "indoor",
        "outdoor",
        "studio",
        "beach",
        "urban",
        "nature",
        "bedroom",
        "bathroom",
        "gym",
        "office",
        "car",
        "nightclub",
        "domestic",
        "pool",
        "forest",
        "street",
        "kitchen",
        "living_room",
        "mirror_selfie",
    ],
    "location": [
        "bedroom",
        "living_room",
        "bathroom",
        "kitchen",
        "beach",
        "pool",
        "forest",
        "street",
        "car",
        "office",
        "gym",
        "mirror_selfie",
        "studio",
        "outdoor_unspecified",
        "indoor_unspecified",
    ],
    "lighting": [
        "natural",
        "studio",
        "soft",
        "harsh",
        "golden_hour",
        "dim",
        "bright",
        "backlit",
        "neon",
        "flash",
        "candlelight",
    ],
    "mood": [
        "candid",
        "posed",
        "casual",
        "glamour",
        "artistic",
        "intimate",
        "playful",
        "sensual",
        "dramatic",
        "editorial",
        "street",
    ],
    "clothing": None,  # free-form list
    "person": None,  # free-form name
    "tags": None,  # free-form keywords
    "caption": None,  # free-form text
}

# Mappings for common out-of-range values → nearest valid enum
REMAP = {
    "rating": {
        "title_card": "sfw",
        "black_screen": "sfw",
        "text_only": "sfw",
        "safe": "sfw",
        "nsfw_content": "nsfw",
        "adult": "nsfw",
        "explicit": "nsfw",
        "mild": "suggestive",
        "risque": "suggestive",
    },
    "content_type": {
        "title_card": "portrait",
        "black_screen": "portrait",
        "text": "portrait",
        "full": "full_body",
        "upper_body": "bust",
        "waist_up": "half_body",
        "knees_up": "three_quarter",
        "bodyscape": "bodyscape",
    },
    "setting": {
        "inside": "indoor",
        "outside": "outdoor",
        "room": "indoor",
        "house": "indoor",
        "apartment": "indoor",
        "domestic": "domestic",
    },
    "pose": {
        "standing_up": "standing",
        "seated": "sitting",
        "lying": "laying",
        "lay": "laying",
        "on_back": "laying",
        "on_stomach": "laying",
        "on_knees": "kneeling",
        "bent_over": "bending",
    },
    "location": {
        "other_indoor": "indoor_unspecified",
        "other_outdoor": "outdoor_unspecified",
        "unknown": "indoor_unspecified",
    },
    "lighting": {
        "sunlight": "natural",
        "daylight": "natural",
        "artificial": "studio",
        "dark": "dim",
        "low_light": "dim",
        "ring_light": "studio",
        "window_light": "natural",
    },
    "mood": {
        "sexy": "sensual",
        "erotic": "sensual",
        "fun": "playful",
        "serious": "dramatic",
        "professional": "editorial",
        "selfie_mood": "casual",
    },
}


def validate_and_correct_tags(tags: dict) -> tuple[dict, list[str]]:
    """
    Validate all tag values against allowed enums.
    Remap out-of-range values to nearest valid entry.
    Returns corrected tags dict + validation_report.
    """
    corrected: dict[str, Any] = {}
    report: list[str] = []

    for category, values in tags.items():
        allowed = ALLOWED_ENUMS.get(category)

        if allowed is None:
            # Free-form category — pass through
            corrected[category] = values
            continue

        if isinstance(values, list):
            fixed = []
            for v in values:
                v_str = str(v).strip().lower()
                if v_str in allowed:
                    fixed.append(v_str)
                else:
                    # Try remap
                    remapped = REMAP.get(category, {}).get(v_str)
                    if remapped:
                        fixed.append(remapped)
                        report.append(f"REMAP {category}: '{v}' → '{remapped}'")
                    else:
                        # Clamp to first valid value
                        fallback = allowed[0]
                        fixed.append(fallback)
                        report.append(
                            f"CLAMP {category}: '{v}' → '{fallback}' (default)"
                        )
            corrected[category] = fixed
        else:
            v_str = str(values).strip().lower()
            if v_str in allowed:
                corrected[category] = v_str
            else:
                remapped = REMAP.get(category, {}).get(v_str)
                if remapped:
                    corrected[category] = remapped
                    report.append(f"REMAP {category}: '{values}' → '{remapped}'")
                else:
                    fallback = allowed[0]
                    corrected[category] = fallback
                    report.append(
                        f"CLAMP {category}: '{values}' → '{fallback}' (default)"
                    )

    return corrected, report
