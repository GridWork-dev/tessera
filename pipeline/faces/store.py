"""Face-vector store — thin raw-sqlite3 layer over ``people`` + ``faces`` (009).

Deliberately raw sqlite3 (not the SQLAlchemy ORM in ``pipeline/database.py``) so
this lane owns disjoint files and never edits the shared schema module. The
store is the privacy boundary's write side: it is where biometric vectors live
and where erasure happens.

Embeddings are packed as float32 little-endian blobs sized to ``embedding_dim``.
``delete_person`` performs ERASURE (faces then the person row); ``purge_all_faces``
is the panic switch.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def pack_embedding(vec: np.ndarray) -> bytes:
    """np float vector -> float32 little-endian bytes."""
    return np.ascontiguousarray(vec, dtype="<f4").tobytes()


def unpack_embedding(blob: bytes, dim: int) -> np.ndarray:
    """float32 little-endian bytes -> np.ndarray of length ``dim``."""
    arr = np.frombuffer(blob, dtype="<f4")
    if dim and arr.size != dim:
        raise ValueError(f"embedding length {arr.size} != expected dim {dim}")
    return np.array(arr, dtype=np.float32)


class FaceStore:
    """CRUD + clustering support + erasure over the faces/people tables."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ---- writes ---------------------------------------------------------- #
    def add_face(
        self,
        image_id: int,
        bbox: list[float],
        embedding: np.ndarray,
        embedding_dim: int,
        detector: str,
        embedder: str,
        confidence: float,
        person_id: int | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO faces
                   (image_id, person_id, bbox, embedding_blob, embedding_dim,
                    detector, embedder, confidence, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    image_id,
                    person_id,
                    json.dumps(bbox),
                    pack_embedding(embedding),
                    embedding_dim,
                    detector,
                    embedder,
                    confidence,
                    _now(),
                ),
            )
            face_id = int(cur.lastrowid)
            if person_id is not None:
                self._refresh_person(conn, person_id)
            return face_id

    def create_person(self, name: str | None = None) -> int:
        with self._connect() as conn:
            now = _now()
            cur = conn.execute(
                "INSERT INTO people (name, face_count, created_at, updated_at) "
                "VALUES (?, 0, ?, ?)",
                (name, now, now),
            )
            return int(cur.lastrowid)

    def assign_face(self, face_id: int, person_id: int | None) -> None:
        with self._connect() as conn:
            prev = conn.execute(
                "SELECT person_id FROM faces WHERE id = ?", (face_id,)
            ).fetchone()
            conn.execute(
                "UPDATE faces SET person_id = ? WHERE id = ?", (person_id, face_id)
            )
            for pid in {person_id, prev["person_id"] if prev else None}:
                if pid is not None:
                    self._refresh_person(conn, pid)

    def name_person(self, person_id: int, name: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE people SET name = ?, updated_at = ? WHERE id = ?",
                (name, _now(), person_id),
            )

    def merge_people(self, source_id: int, target_id: int) -> None:
        """Move all of source's faces to target, then delete the empty source."""
        if source_id == target_id:
            return
        with self._connect() as conn:
            conn.execute(
                "UPDATE faces SET person_id = ? WHERE person_id = ?",
                (target_id, source_id),
            )
            conn.execute("DELETE FROM people WHERE id = ?", (source_id,))
            self._refresh_person(conn, target_id)

    def split_face(self, face_id: int) -> int:
        """Detach a face into a brand-new unnamed person; return new person id."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT person_id FROM faces WHERE id = ?", (face_id,)
            ).fetchone()
            old_pid = row["person_id"] if row else None
            now = _now()
            cur = conn.execute(
                "INSERT INTO people (name, face_count, created_at, updated_at) "
                "VALUES (NULL, 0, ?, ?)",
                (now, now),
            )
            new_pid = int(cur.lastrowid)
            conn.execute(
                "UPDATE faces SET person_id = ? WHERE id = ?", (new_pid, face_id)
            )
            self._refresh_person(conn, new_pid)
            if old_pid is not None:
                self._refresh_person(conn, old_pid)
            return new_pid

    def delete_person(self, person_id: int) -> int:
        """ERASURE: delete the person AND all their face vectors.

        Returns the number of face rows removed. This is the GDPR/BIPA
        right-to-erasure path — biometric data is hard-deleted.
        """
        with self._connect() as conn:
            n = conn.execute(
                "DELETE FROM faces WHERE person_id = ?", (person_id,)
            ).rowcount
            conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
            return int(n)

    def purge_all_faces(self) -> int:
        """PANIC: wipe the entire face store (all faces + all people)."""
        with self._connect() as conn:
            n = conn.execute("DELETE FROM faces").rowcount
            conn.execute("DELETE FROM people")
            return int(n)

    def _refresh_person(self, conn: sqlite3.Connection, person_id: int) -> None:
        row = conn.execute(
            "SELECT COUNT(*) AS n, MIN(id) AS cover FROM faces WHERE person_id = ?",
            (person_id,),
        ).fetchone()
        conn.execute(
            "UPDATE people SET face_count = ?, cover_face_id = ?, updated_at = ? "
            "WHERE id = ?",
            (row["n"], row["cover"], _now(), person_id),
        )

    # ---- reads ----------------------------------------------------------- #
    def list_people(self) -> list[dict[str, Any]]:
        # Join the cover face's source image so the grid can render a cover
        # thumbnail directly (file_hash) without a per-person detail round-trip.
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT p.id, p.name, p.cover_face_id, p.face_count, p.created_at, "
                "p.updated_at, f.image_id AS cover_image_id, "
                "i.file_hash AS cover_image_hash "
                "FROM people p LEFT JOIN faces f ON f.id = p.cover_face_id "
                "LEFT JOIN images i ON i.id = f.image_id "
                "ORDER BY p.face_count DESC, p.id ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def faces_for_image(self, image_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT f.id, f.image_id, f.person_id, f.bbox, f.embedding_dim, "
                "f.detector, f.embedder, f.confidence, f.created_at, "
                "i.file_hash AS file_hash "
                "FROM faces f LEFT JOIN images i ON i.id = f.image_id "
                "WHERE f.image_id = ?",
                (image_id,),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def faces_for_person(self, person_id: int) -> list[dict[str, Any]]:
        # Include each face's source-image file_hash so the faces grid renders
        # thumbnails without a getImageDetail fetch per face (was an unbounded N+1).
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT f.id, f.image_id, f.person_id, f.bbox, f.embedding_dim, "
                "f.detector, f.embedder, f.confidence, f.created_at, "
                "i.file_hash AS file_hash "
                "FROM faces f LEFT JOIN images i ON i.id = f.image_id "
                "WHERE f.person_id = ?",
                (person_id,),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def unclustered_faces(self, embedder: str) -> list[tuple[int, np.ndarray]]:
        """(face_id, vector) for faces of one embedder with no person assigned."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, embedding_blob, embedding_dim FROM faces "
                "WHERE person_id IS NULL AND embedder = ?",
                (embedder,),
            ).fetchall()
            return [
                (
                    int(r["id"]),
                    unpack_embedding(r["embedding_blob"], r["embedding_dim"]),
                )
                for r in rows
            ]

    def all_face_vectors(self, embedder: str) -> list[tuple[int, np.ndarray]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, embedding_blob, embedding_dim FROM faces WHERE embedder = ?",
                (embedder,),
            ).fetchall()
            return [
                (
                    int(r["id"]),
                    unpack_embedding(r["embedding_blob"], r["embedding_dim"]),
                )
                for r in rows
            ]

    @staticmethod
    def _row_to_dict(r: sqlite3.Row) -> dict[str, Any]:
        d = dict(r)
        if d.get("bbox"):
            d["bbox"] = json.loads(d["bbox"])
        return d
