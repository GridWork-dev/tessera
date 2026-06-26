"""Shared singletons for the split-out route modules.

main.py creates the real instances and calls init() at import; route modules read
these at REQUEST time (e.g. deps.db.get_session()), never capture them at import,
so the test fixtures that pop + re-import webui.main (resetting these via a fresh
init()) see the new bindings (D-TEST-DBBIND). collection_items_t is a stateless
table object and is fine as a module constant.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import column, table

db: Any = None
thumb_cache: Any = None
grid_gen: Any = None

# Raw-SQL table for collection_items (migration 002; no ORM model).
collection_items_t = table(
    "collection_items", column("image_id"), column("collection_id")
)


def init(*, database: Any, thumbs: Any, grids: Any) -> None:
    """(Re)bind the shared singletons. Called by webui.main at import time."""
    global db, thumb_cache, grid_gen
    db = database
    thumb_cache = thumbs
    grid_gen = grids
