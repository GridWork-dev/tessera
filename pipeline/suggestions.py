"""Exclude/hide suggestions mined from the operator's reject decisions.

Read-only, no embeddings — works today. Aggregates the TAGS + reject REASONS of
images the operator rejected (``images.flag_action='reject'`` +
``user_labels(category='reject_reason')``) into ranked candidate exclusion rules,
so recurring junk can be hidden in one click. Degrades to an empty list when
there are no rejects yet.

The candidate (category, value) pairs map 1:1 onto ``exclusion_rules`` rows, which
Browse already honors via ``exclude=true``. Pairs already excluded are filtered out.
"""

from __future__ import annotations

from typing import Any

DEFAULT_MIN_COUNT = 3


def exclusion_candidates(
    db, min_count: int = DEFAULT_MIN_COUNT, limit: int = 50
) -> dict[str, Any]:
    """Rank tags frequent among REJECTED images as candidate hide rules.

    Returns ``{candidates, reasons, reject_count, min_count}`` where each
    candidate is ``{category, value, reject_count, sample_image_ids}`` for tags
    appearing on ``>= min_count`` distinct rejected images and not already
    excluded. ``reasons`` is the top reject-reason-chip tally (context).
    """
    from sqlalchemy import func, text

    from pipeline.database import ExclusionRule, Image, Tag

    min_count = max(1, int(min_count))
    with db.get_session() as session:
        # Join against a subquery (NOT an IN-list) so this scales past SQLite's
        # ~999 bound-variable limit as rejects grow.
        reject_sq = (
            session.query(Image.id).filter(Image.flag_action == "reject").subquery()
        )
        reject_count = int(
            session.query(func.count()).select_from(reject_sq).scalar() or 0
        )
        if reject_count == 0:
            return {
                "candidates": [],
                "reasons": [],
                "reject_count": 0,
                "min_count": min_count,
            }

        existing = {
            (c, v)
            for c, v in session.query(ExclusionRule.category, ExclusionRule.value).all()
        }

        n_distinct = func.count(func.distinct(Tag.image_id))
        rows = (
            session.query(Tag.category, Tag.value, n_distinct.label("n"))
            .join(reject_sq, Tag.image_id == reject_sq.c.id)
            .filter(Tag.category != "rating")
            .group_by(Tag.category, Tag.value)
            .having(n_distinct >= min_count)
            .order_by(n_distinct.desc())
            .all()
        )

        candidates: list[dict[str, Any]] = []
        for cat, val, n in rows:
            if (cat, val) in existing:
                continue
            samples = [
                r[0]
                for r in session.query(Tag.image_id)
                .join(reject_sq, Tag.image_id == reject_sq.c.id)
                .filter(Tag.category == cat, Tag.value == val)
                .limit(4)
                .all()
            ]
            candidates.append(
                {
                    "category": cat,
                    "value": val,
                    "reject_count": int(n),
                    "sample_image_ids": samples,
                }
            )
            if len(candidates) >= limit:
                break

        # user_labels is a raw-SQL migration table (no ORM model); guard its
        # absence (fresh/un-migrated DBs) so mining degrades to no-reasons rather
        # than erroring.
        try:
            reason_rows = session.execute(
                text(
                    "SELECT value, COUNT(*) AS n FROM user_labels "
                    "WHERE category = 'reject_reason' "
                    "GROUP BY value ORDER BY n DESC LIMIT 12"
                )
            ).fetchall()
            reasons = [{"value": r[0], "count": int(r[1])} for r in reason_rows]
        except Exception:
            reasons = []

        return {
            "candidates": candidates,
            "reasons": reasons,
            "reject_count": reject_count,
            "min_count": min_count,
        }
