"""Caption keyword (FTS5) lane for the search service.

Extracted from ``webui.search`` (pure mechanical move — no behavior change).
``webui.search`` re-exports every symbol defined here, so existing references
such as ``webui.search._caption_fts`` / ``search_svc.CAPTION_FTS_TABLE`` keep
working unchanged.

This is the standalone caption keyword lane plus the FTS helpers used by RRF
fusion. It never touches vectors or the text tower.
"""

from __future__ import annotations

import os
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

# RRF constant from the spec (k ~= 60).
RRF_K = 60

# Caption FTS5 over the ``captions`` table (migration 008, built + populated via
# pipeline.database.rebuild_caption_fts). Set to the table name so the caption
# keyword lane + RRF fusion activate automatically when the full Tier-2 caption
# run lands (it is a statistical no-op while captions are near-empty). Env-
# overridable to "" to disable.
CAPTION_FTS_TABLE: str | None = (
    os.environ.get("CAPTION_FTS_TABLE", "captions_fts") or None
)


def _fts_match_query(q: str | None) -> str | None:
    """Build a safe FTS5 MATCH expression from a free-text query.

    Extracts word tokens and quotes each as a phrase (space == implicit AND in
    FTS5), so user input can never inject FTS operators / syntax errors. Returns
    None when there is nothing to match.
    """
    if not q:
        return None
    terms = re.findall(r"\w+", q.lower())
    if not terms:
        return None
    return " ".join(f'"{t}"' for t in terms)


def _caption_phrase_match(q: str | None) -> str | None:
    """Sanitize a free-text query into a single quoted FTS5 phrase.

    Wraps the whole query as one double-quoted phrase, escaping any embedded
    double-quotes (FTS5 escapes ``"`` by doubling it). Quoting the phrase means
    punctuation in the user's query can never be parsed as an FTS5 operator and
    raise a syntax error. Returns None when there is nothing to match.
    """
    if not q or not q.strip():
        return None
    escaped = q.strip().replace('"', '""')
    return f'"{escaped}"'


def _caption_search(
    session: Session, q: str | None, candidate_ids: list[int]
) -> list[int]:
    """Standalone caption keyword lane -> image_ids ordered by bm25 (best first).

    Matches the caption FTS5 table (``CAPTION_FTS_TABLE``) on a sanitized quoted
    phrase, intersects with the existing candidate set (so tag/rating/person/
    processed filters still apply), and orders by ``bm25(<table>)`` ascending
    (lower bm25 == better match). Degrades to ``[]`` (not an error) when the lane
    is disabled, the query has no content, or the FTS table is absent on this DB.
    """
    if CAPTION_FTS_TABLE is None:
        return []
    match = _caption_phrase_match(q)
    if not match:
        return []
    if (
        session.execute(
            text(
                "SELECT 1 FROM sqlite_master "
                "WHERE name = :n AND type IN ('table', 'view')"
            ),
            {"n": CAPTION_FTS_TABLE},
        ).first()
        is None
    ):
        return []
    # CAPTION_FTS_TABLE is a module constant (never user input) -> safe to inline.
    sql = text(
        f"SELECT image_id FROM {CAPTION_FTS_TABLE} "  # noqa: S608
        f"WHERE {CAPTION_FTS_TABLE} MATCH :q "
        f"ORDER BY bm25({CAPTION_FTS_TABLE})"
    )
    rows = session.execute(sql, {"q": match}).fetchall()
    ids = [int(r[0]) for r in rows]
    if candidate_ids is not None:
        allow = set(candidate_ids)
        ids = [i for i in ids if i in allow]
    return ids


def _caption_fts(
    session: Session, q: str, candidate_ids: list[int] | None
) -> list[int]:
    """Caption FTS5 match -> image_ids best-first, constrained to candidates.

    Returns [] when: the lane is disabled (CAPTION_FTS_TABLE is None), the query
    has no usable terms, OR the FTS table does not exist on this DB (migration 008
    not applied / an older backup). Filters by the candidate set in Python (not a
    huge SQL ``IN``) since the FTS match is naturally small and the candidate set
    can be the whole corpus.
    """
    if CAPTION_FTS_TABLE is None:
        return []
    match = _fts_match_query(q)
    if not match:
        return []
    # Degrade gracefully if the FTS table isn't built here (CAPTION_FTS_TABLE now
    # defaults to a non-None name, so a missing table would otherwise raise
    # OperationalError). Mirror rebuild_caption_fts's sqlite_master probe.
    if (
        session.execute(
            text(
                "SELECT 1 FROM sqlite_master "
                "WHERE name = :n AND type IN ('table', 'view')"
            ),
            {"n": CAPTION_FTS_TABLE},
        ).first()
        is None
    ):
        return []
    # CAPTION_FTS_TABLE is a module constant (never user input) -> safe to inline.
    sql = text(
        f"SELECT image_id FROM {CAPTION_FTS_TABLE} "  # noqa: S608
        f"WHERE {CAPTION_FTS_TABLE} MATCH :q ORDER BY rank"
    )
    rows = session.execute(sql, {"q": match}).fetchall()
    ids = [int(r[0]) for r in rows]
    if candidate_ids is not None:
        allow = set(candidate_ids)
        ids = [i for i in ids if i in allow]
    return ids
