"""Label store — raw sqlite3 over label_sets / label_definitions / user_labels.

Mirrors pipeline/faces/store.py: disjoint files, never edits the shared schema
module. Single-select sets are enforced HERE (assign deletes prior values for
that set+image) because SQLite partial-unique-index predicates can't reference
label_sets. user_labels.category is NOT NULL legacy; we store the set name there.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class LabelStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ---- reads ----------------------------------------------------------- #
    def list_sets(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            sets = [
                dict(r)
                for r in conn.execute(
                    "SELECT id, name, single_select, color, sort_order, is_system "
                    "FROM label_sets ORDER BY sort_order, id"
                ).fetchall()
            ]
            for s in sets:
                s["values"] = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT id, value, color, sort_order FROM label_definitions "
                        "WHERE set_id = ? ORDER BY sort_order, id",
                        (s["id"],),
                    ).fetchall()
                ]
            return sets

    def labels_for_image(self, image_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT id, image_id, set_id, category, value FROM user_labels "
                    "WHERE image_id = ? AND set_id IS NOT NULL ORDER BY id",
                    (image_id,),
                ).fetchall()
            ]

    # ---- set / value mutations ------------------------------------------- #
    def create_set(
        self, name: str, single_select: bool = False, color: str | None = None
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO label_sets (name, single_select, color) VALUES (?, ?, ?)",
                (name, 1 if single_select else 0, color),
            )
            return int(cur.lastrowid)

    def update_set(
        self,
        set_id: int,
        *,
        name: str | None = None,
        single_select: bool | None = None,
        color: str | None = None,
        sort_order: int | None = None,
    ) -> None:
        """Patch a set's name / single_select / color / sort_order.

        Only the provided fields change (None = leave as-is). ``color`` cannot be
        cleared to NULL through this method (None means "unchanged") — a deliberate
        limitation; clearing a color is not a product need.
        """
        fields: list[str] = []
        params: list[Any] = []
        if name is not None:
            fields.append("name = ?")
            params.append(name)
        if single_select is not None:
            fields.append("single_select = ?")
            params.append(1 if single_select else 0)
        if color is not None:
            fields.append("color = ?")
            params.append(color)
        if sort_order is not None:
            fields.append("sort_order = ?")
            params.append(sort_order)
        if not fields:
            return
        params.append(set_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE label_sets SET {', '.join(fields)} WHERE id = ?", params
            )

    def delete_set(self, set_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM user_labels WHERE set_id = ?", (set_id,))
            conn.execute("DELETE FROM label_definitions WHERE set_id = ?", (set_id,))
            conn.execute("DELETE FROM label_sets WHERE id = ?", (set_id,))

    def add_value(self, set_id: int, value: str, color: str | None = None) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO label_definitions (set_id, value, color) "
                "VALUES (?, ?, ?)",
                (set_id, value, color),
            )
            if cur.lastrowid:
                return int(cur.lastrowid)
            row = conn.execute(
                "SELECT id FROM label_definitions WHERE set_id = ? AND value = ?",
                (set_id, value),
            ).fetchone()
            return int(row["id"])

    def remove_value(self, value_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM label_definitions WHERE id = ?", (value_id,))

    # ---- assignment ------------------------------------------------------ #
    def assign_label(self, image_id: int, set_id: int, value: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name, single_select FROM label_sets WHERE id = ?", (set_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown label set {set_id}")
            if row["single_select"]:
                conn.execute(
                    "DELETE FROM user_labels WHERE image_id = ? AND set_id = ?",
                    (image_id, set_id),
                )
            cur = conn.execute(
                "INSERT OR IGNORE INTO user_labels "
                "(image_id, set_id, category, value, owner_id) VALUES (?, ?, ?, ?, 1)",
                (image_id, set_id, row["name"], value),
            )
            if cur.lastrowid:
                return int(cur.lastrowid)
            # IGNORE-miss: a row with the same (image_id, category, value) already
            # exists. It may be a legacy row with set_id IS NULL (table-level
            # UNIQUE from migration 002 ignores set_id), so match on category/value
            # without requiring set_id and adopt that row into this set.
            existing = conn.execute(
                "SELECT id FROM user_labels "
                "WHERE image_id = ? AND category = ? AND value = ?",
                (image_id, row["name"], value),
            ).fetchone()
            if existing is None:
                raise ValueError(
                    f"assign_label could not place ({image_id}, {set_id}, {value!r})"
                )
            conn.execute(
                "UPDATE user_labels SET set_id = ? WHERE id = ?",
                (set_id, int(existing["id"])),
            )
            return int(existing["id"])

    def unassign(self, label_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM user_labels WHERE id = ?", (label_id,))
