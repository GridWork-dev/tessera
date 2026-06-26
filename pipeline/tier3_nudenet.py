"""
Tier 3 — NudeNet region detection.

NudeNet output is **metadata only** and is NEVER used as a gate: it populates
``images.nudenet_regions`` (JSON) and sets ``images.nudenet_checked = 1``.
It MUST NOT touch ``images.rating`` — rating is owned by the WD tagger (Tier 0).

Schema written (see database.py:88-91):
    JSON array of {"label": str, "score": float, "box": [x1, y1, x2, y2]}

Heavy deps are imported lazily: the MacBook venv lacks ``nudenet``, so the
module must import + run its pure-logic unit tests without it. Only the
detector load and ``detect_image`` need the real model.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from pipeline.database import Image
from pipeline.paths import resolve_image_path


def convert_regions(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map raw NudeNet detections to the stored schema. PURE — no model needed.

    NudeNet emits ``{'class': str, 'score': float, 'box': [x, y, w, h]}`` with
    a top-left origin and width/height box. The stored schema uses
    ``{'label', 'score', 'box': [x1, y1, x2, y2]}`` with x2=x+w, y2=y+h.
    """
    regions: list[dict[str, Any]] = []
    for det in raw:
        x, y, w, h = det["box"]
        regions.append(
            {
                "label": det["class"],
                "score": round(det["score"], 4),
                "box": [x, y, x + w, y + h],
            }
        )
    return regions


class Tier3NudeNet:
    """Wraps a single NudeDetector instance and writes regions as metadata."""

    def __init__(self) -> None:
        self._detector: Any = None

    def _load(self) -> Any:
        """Lazily construct the NudeDetector (heavy import; box lacks it on MBP)."""
        if self._detector is None:
            from nudenet import NudeDetector  # lazy: MacBook venv has no nudenet

            self._detector = NudeDetector()
        return self._detector

    def detect_image(self, rel_path: str) -> list[dict[str, Any]]:
        """Resolve a relative DB path, run detection, return converted regions."""
        detector = self._load()
        path = resolve_image_path(rel_path)
        raw = detector.detect(str(path))
        return convert_regions(raw)

    def write_regions(
        self, session: Session, image_id: int, regions: list[dict[str, Any]]
    ) -> None:
        """Persist regions as JSON metadata and mark the image checked.

        NEVER sets Image.rating — NudeNet is metadata, never a gate.
        """
        session.query(Image).filter(Image.id == image_id).update(
            {
                "nudenet_regions": json.dumps(regions),
                "nudenet_checked": 1,
            }
        )
        session.commit()
