"""Tier 0 tagger unit tests -- pure label-mapping + preprocessing logic.

These run on the MacBook gate WITHOUT the box-only ``.onnx`` weights (they only
need the small label files shipped in the repo) and WITHOUT torch/transformers.
No real model is loaded; no real DB is touched.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.tier0_tagger import (  # noqa: E402
    JOYTAG_NUM_TAGS,
    JOYTAG_THRESHOLD,
    WD_CAT_CHARACTER,
    WD_CAT_GENERAL,
    WD_CAT_RATING,
    WD_CHARACTER_THRESHOLD,
    WD_GENERAL_THRESHOLD,
    WD_NUM_TAGS,
    load_joytag_labels,
    load_wd_labels,
    map_joytag_logits,
    map_wd_logits,
)


def _logit_for(prob: float) -> float:
    """Inverse sigmoid so we can drive map_* functions at a chosen probability."""
    prob = min(max(prob, 1e-6), 1 - 1e-6)
    return float(np.log(prob / (1.0 - prob)))


# ---------------------------------------------------------------------------
# Label loading
# ---------------------------------------------------------------------------
def test_joytag_labels_splitlines_count():
    labels = load_joytag_labels()
    # splitlines yields 5813 (NOT 5812 from wc -l; no trailing newline).
    assert len(labels) == JOYTAG_NUM_TAGS == 5813
    assert all(isinstance(t, str) for t in labels)


def test_wd_labels_count_and_category_split():
    labels = load_wd_labels()
    assert len(labels["names"]) == WD_NUM_TAGS == 10861
    assert len(labels["categories"]) == 10861

    cats = labels["categories"]
    n_general = sum(1 for c in cats if c == WD_CAT_GENERAL)
    n_character = sum(1 for c in cats if c == WD_CAT_CHARACTER)
    n_rating = sum(1 for c in cats if c == WD_CAT_RATING)

    # Exactly 4 rating rows (general/sensitive/questionable/explicit).
    assert n_rating == 4
    assert len(labels["rating_indices"]) == 4
    assert len(labels["rating_names"]) == 4
    # Categories partition the corpus.
    assert n_general + n_character + n_rating == 10861
    assert n_general == 8106
    assert n_character == 2751


# ---------------------------------------------------------------------------
# JoyTag logit mapping
# ---------------------------------------------------------------------------
def test_map_joytag_logits_returns_only_above_threshold():
    labels = load_joytag_labels()
    n = len(labels)
    # Everything safely below threshold...
    logits = np.full(n, _logit_for(0.05), dtype=np.float32)
    # ...except two indices pushed above 0.40.
    above = [10, 4321]
    for i in above:
        logits[i] = _logit_for(0.92)

    out = map_joytag_logits(logits, labels)
    returned = {value for value, _ in out}
    assert returned == {labels[i] for i in above}
    assert len(out) == 2
    for _, score in out:
        assert score >= JOYTAG_THRESHOLD


# ---------------------------------------------------------------------------
# WD logit mapping
# ---------------------------------------------------------------------------
def test_map_wd_logits_category_routing():
    labels = load_wd_labels()
    cats = labels["categories"]

    # Pick one general index and one character index from the real labels.
    general_idx = cats.index(WD_CAT_GENERAL)
    character_idx = cats.index(WD_CAT_CHARACTER)
    rating_indices = labels["rating_indices"]

    # WD-EVA02 outputs probabilities directly (map_wd_logits does NOT sigmoid),
    # so feed probabilities here, not pre-sigmoid logits.
    logits = np.full(len(cats), 0.01, dtype=np.float32)
    # General tag above 0.35.
    logits[general_idx] = 0.70
    # Character tag above 0.85.
    logits[character_idx] = 0.95
    # Make the SECOND rating prob the argmax winner.
    winner_rating = rating_indices[1]
    logits[winner_rating] = 0.88

    out = map_wd_logits(logits, labels)
    by_cat: dict[str, list[tuple[str, float]]] = {}
    for category, value, score in out:
        by_cat.setdefault(category, []).append((value, score))

    # general -> 'tags'
    assert "tags" in by_cat
    assert labels["names"][general_idx] in {v for v, _ in by_cat["tags"]}

    # character -> 'person'
    assert "person" in by_cat
    assert by_cat["person"][0][0] == labels["names"][character_idx]

    # rating -> 'rating', exactly one, = argmax of the 4 rating logits.
    assert "rating" in by_cat
    assert len(by_cat["rating"]) == 1
    assert by_cat["rating"][0][0] == labels["names"][winner_rating]


def test_wd_general_threshold_is_045():
    """Locked decision 2026-06-23: WD general floor raised 0.35 -> 0.45."""
    assert WD_GENERAL_THRESHOLD == 0.45


def test_map_wd_logits_excludes_general_tag_in_old_band():
    """A 0.42 general tag (included at the old 0.35 floor) is now excluded."""
    labels = load_wd_labels()
    cats = labels["categories"]
    general_idx = cats.index(WD_CAT_GENERAL)

    logits = np.full(len(cats), 0.01, dtype=np.float32)
    logits[general_idx] = 0.42  # in the old 0.35-0.45 noisy band

    out = map_wd_logits(labels=labels, logits=logits)
    values = {value for _, value, _ in out}
    assert labels["names"][general_idx] not in values


def test_map_wd_logits_thresholds_exclude_low_scores():
    labels = load_wd_labels()
    cats = labels["categories"]
    general_idx = cats.index(WD_CAT_GENERAL)
    character_idx = cats.index(WD_CAT_CHARACTER)

    logits = np.full(len(cats), 0.01, dtype=np.float32)
    # General just below 0.35 -> excluded.
    logits[general_idx] = WD_GENERAL_THRESHOLD - 0.05
    # Character at 0.80 (below 0.85) -> excluded.
    logits[character_idx] = WD_CHARACTER_THRESHOLD - 0.05

    out = map_wd_logits(logits, labels)
    values = {value for _, value, _ in out}
    assert labels["names"][general_idx] not in values
    assert labels["names"][character_idx] not in values
    # A rating tag is ALWAYS emitted (argmax), so output is never empty.
    rating_rows = [r for r in out if r[0] == "rating"]
    assert len(rating_rows) == 1
