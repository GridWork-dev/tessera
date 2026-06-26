"""
Tier 2 — VLM captions via the warm mlx Qwen2.5-VL server on 127.0.0.1:8081.

This is the Tier-2 path (the legacy OllamaTagger at :11434 is NOT used here and
is left untouched). It mirrors tier1_embedder's shape: a thin client plus a
resume-safe `caption_unprocessed` pass that writes one row per image into the
`captions` table (UNIQUE(image_id, model)) and commits per image.

The mlx server reads image files locally (on-box), so the request sends the
ABSOLUTE image path as the image_url — no base64, no upload. Captions are free
text (matches the captions schema + ADR-0001; avoids JSON-fence fragility).

Resume: an image is captioned only if it has no `captions` row for this model.
Priority: explicit > questionable > sensitive > general (the WD rating head),
so a reboot mid-sweep leaves the most useful captions on disk first.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

import requests

from pipeline.database import apply_sqlite_pragmas
from pipeline.paths import resolve_image_path

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:8081"
DEFAULT_MODEL = "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"
DEFAULT_PROMPT = (
    "Describe this image for a searchable media catalog. In 1-3 concise, factual "
    "sentences, cover the subject, pose, clothing or state of dress, setting, and "
    "any notable visual attributes. Do not editorialize or add a preamble."
)

# Priority order for the resume sweep, by the WD rating-head value.
_RATING_PRIORITY_CASE = (
    "CASE r.value "
    "WHEN 'explicit' THEN 0 "
    "WHEN 'questionable' THEN 1 "
    "WHEN 'sensitive' THEN 2 "
    "WHEN 'general' THEN 3 "
    "ELSE 4 END"
)


def select_uncaptioned(
    conn: sqlite3.Connection,
    model: str,
    limit: int,
    person: str | None = None,
    rating_values: list[str] | None = None,
) -> list[tuple]:
    """Return up to ``limit`` (id, path, person) rows lacking a caption for ``model``.

    Ordered by WD-rating priority then id. ``rating_values`` (e.g.
    ['explicit', 'questionable']) scopes the sweep to a rating subset.
    """
    sql = """
        SELECT i.id, i.path, i.person
        FROM images i
        LEFT JOIN captions c
            ON c.image_id = i.id AND c.model = ?
        LEFT JOIN tags r
            ON r.image_id = i.id AND r.category = 'rating' AND r.tag_source = 'wd_eva02'
        WHERE c.id IS NULL
    """
    params: list[Any] = [model]
    if person:
        sql += " AND i.person = ?"
        params.append(person)
    if rating_values:
        placeholders = ",".join("?" for _ in rating_values)
        sql += f" AND r.value IN ({placeholders})"
        params.extend(rating_values)
    sql += f" ORDER BY {_RATING_PRIORITY_CASE}, i.id LIMIT ?"
    params.append(limit)
    return conn.execute(sql, params).fetchall()


class Tier2Captioner:
    """Client + resume-safe caption pass against the mlx Qwen2.5-VL server."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        prompt: str = DEFAULT_PROMPT,
        max_tokens: int = 160,
        temperature: float = 0.2,
        timeout: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.prompt = prompt
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

    def health(self) -> bool:
        """True if the mlx server reports a healthy status; False on any error."""
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=5)
            return bool(resp.ok) and resp.json().get("status") == "healthy"
        except Exception:
            return False

    def caption_image(self, rel_path: str) -> str:
        """Caption one image (DB-relative path) via /v1/chat/completions.

        Sends the ABSOLUTE path as the image_url (server reads it locally — no
        base64). Returns the stripped caption text.
        """
        abs_path = resolve_image_path(rel_path)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self.prompt},
                        {"type": "image_url", "image_url": {"url": str(abs_path)}},
                    ],
                }
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        resp = requests.post(
            f"{self.base_url}/v1/chat/completions", json=payload, timeout=self.timeout
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def caption_unprocessed(
        self,
        db: Any,
        limit: int = 200,
        person: str | None = None,
        rating_values: list[str] | None = None,
    ) -> int:
        """Caption images that lack a row for this model; commit per image.

        Idempotent via INSERT OR IGNORE on UNIQUE(image_id, model): a re-run
        selects only still-uncaptioned images, so a crash resumes cleanly.
        Returns the number of captions written this call.
        """
        conn = sqlite3.connect(db.db_path)
        apply_sqlite_pragmas(conn)
        written = 0
        try:
            rows = select_uncaptioned(conn, self.model, limit, person, rating_values)
            for image_id, rel_path, _person in rows:
                try:
                    caption = self.caption_image(rel_path)
                except Exception as exc:  # pragma: no cover - per-image I/O
                    logger.warning("caption failed for id=%s: %s", image_id, exc)
                    continue
                if not caption or not caption.strip():
                    # Empty/whitespace/refusal: do NOT persist, else WHERE c.id IS
                    # NULL would skip this image forever. Leave it selectable.
                    logger.warning("empty caption for id=%s; not persisting", image_id)
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO captions (image_id, model, caption) "
                    "VALUES (?, ?, ?)",
                    (image_id, self.model, caption),
                )
                conn.commit()  # per-image durability
                written += 1
            return written
        finally:
            conn.close()
