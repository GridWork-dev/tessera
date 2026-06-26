"""
Tier 1 — SigLIP SO400M image embeddings.

Produces L2-normalized 1152-dim embeddings (``google/siglip-so400m-patch14-384``,
hidden_size 1152) and persists them to two cooperating stores:

* a turbovec ``IdMapIndex`` (4-bit TurboQuant) at ``data/turbovec_siglip.idx``
  for fast approximate ANN, keyed by ``images.id``; and
* a sqlite-vec ``vec0`` virtual table ``vec_siglip_1152`` (float[1152], cosine)
  for an exact float rescore of the ANN shortlist.

This module is NEW and stands alongside the stale ``pipeline/embedder.py``
(768-dim ``vec_embeddings``). It NEVER touches ``vec_embeddings`` or the
768-dim SigLIP-base path — both stores it creates are independent.

Heavy deps are imported lazily: the MacBook venv has numpy / onnxruntime /
pillow / turbovec / sqlite-vec but NOT torch / transformers. So torch +
transformers are imported inside ``_load`` only; the module imports and its
pure-logic / turbovec tests run without them. numpy, PIL, turbovec, sqlite-vec
are safe at module top.

GROUND TRUTH (introspected on the box, transformers 5.12.1):
    inputs = processor(images=img, return_tensors='pt')
    out = model.get_image_features(**inputs)   # BaseModelOutputWithPooling
    emb = out.pooler_output                     # shape (1, 1152)
Read ``.pooler_output`` — NOT a bare tensor, NOT ``.last_hidden_state`` mean-pool.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image as PILImage

try:
    import sqlite_vec
except ImportError:  # pragma: no cover - sqlite-vec is present in both venvs
    sqlite_vec = None

from pipeline.paths import REPO_ROOT, resolve_image_path

logger = logging.getLogger(__name__)

# Persisted store locations (relative to repo root).
DEFAULT_INDEX_PATH = REPO_ROOT / "data" / "turbovec_siglip.idx"
VEC_TABLE = "vec_siglip_1152"


def _turbovec():
    """Lazily import the native ``turbovec`` ANN backend.

    Kept out of module import so the app (browse + keyword / caption search)
    loads on platforms without a turbovec wheel — e.g. x86_64 macOS, where the
    Apple-Silicon ANN wheel is absent (see the requirements marker). The ANN
    index is only needed for *vector* search, which already degrades gracefully
    when vectors are absent; this raises a clear error only if an ANN operation
    is actually attempted without the backend installed.
    """
    try:
        import turbovec
    except ImportError as e:  # pragma: no cover - exercised on non-arm platforms
        raise RuntimeError(
            "turbovec (the ANN backend for vector search) is not installed for "
            "this platform. Install it on Apple Silicon, or use keyword / "
            "caption search, which does not require it."
        ) from e
    return turbovec


def l2_normalize(vec: np.ndarray) -> np.ndarray:
    """L2-normalize a 1-D vector. PURE — returns float32, safe on zero vectors."""
    vec = np.asarray(vec, dtype=np.float32).ravel()
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        return vec
    return (vec / norm).astype(np.float32)


def serialize_float32(vec: np.ndarray) -> bytes:
    """Pack a float32 vector to raw bytes for sqlite-vec."""
    return np.asarray(vec, dtype=np.float32).tobytes()


class TurboVecStore:
    """Thin wrapper over turbovec ``IdMapIndex`` (real 0.8.0 API).

    Observed API on the box::

        idx = turbovec.IdMapIndex(dim=<positive multiple of 8>, bit_width=4)
        idx.add_with_ids(vectors: float32 (n, d), ids: uint64 (n,))
        scores, ids = idx.search(queries: float32 (nq, d), k, *, allowlist=None)
            # scores float32 (nq, k); ids uint64 (nq, k)
        idx.contains(id) -> bool
        idx.write(path); IdMapIndex.load(path) -> idx
        idx.dim -> int ; idx.bit_width -> int   (properties, NOT callables)

    ``dim`` must be a positive multiple of 8 (1152 qualifies). ``add_with_ids``
    raises ``ValueError`` if an id is already present.
    """

    def __init__(
        self,
        dim: int = 1152,
        bit_width: int = 4,
        path: str | Path = DEFAULT_INDEX_PATH,
    ) -> None:
        self.dim = dim
        self.bit_width = bit_width
        self.path = Path(path)
        self.index = self._open()

    def _open(self) -> Any:
        """Load an existing .idx if present, else build a fresh index."""
        if self.path.exists():
            idx = _turbovec().IdMapIndex.load(str(self.path))
            logger.info("Loaded turbovec index %s (dim=%s)", self.path, idx.dim)
            return idx
        return _turbovec().IdMapIndex(dim=self.dim, bit_width=self.bit_width)

    def contains(self, image_id: int) -> bool:
        return bool(self.index.contains(int(image_id)))

    def add(self, image_id: int, vector: np.ndarray) -> None:
        """Add a single (id, vector). No-op if the id is already indexed."""
        if self.contains(image_id):
            return
        vecs = np.asarray(vector, dtype=np.float32).reshape(1, self.dim)
        ids = np.array([int(image_id)], dtype=np.uint64)
        self.index.add_with_ids(vecs, ids)

    def add_batch(self, image_ids: list[int], vectors: np.ndarray) -> None:
        """Add many (ids, vectors). Skips ids already present."""
        new_ids: list[int] = []
        new_rows: list[np.ndarray] = []
        mat = np.asarray(vectors, dtype=np.float32).reshape(-1, self.dim)
        for image_id, row in zip(image_ids, mat):
            if self.contains(image_id):
                continue
            new_ids.append(int(image_id))
            new_rows.append(row)
        if not new_ids:
            return
        self.index.add_with_ids(
            np.asarray(new_rows, dtype=np.float32),
            np.asarray(new_ids, dtype=np.uint64),
        )

    def search(self, query: np.ndarray, k: int = 20) -> list[tuple[int, float]]:
        """Return up to ``k`` (image_id, score) pairs, best first."""
        q = np.asarray(query, dtype=np.float32).reshape(1, self.dim)
        scores, ids = self.index.search(q, k)
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0])]

    def save(self) -> None:
        """Persist the index to ``self.path`` (creates ``data/`` if needed)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.index.write(str(self.path))
        logger.info("Wrote turbovec index -> %s", self.path)


def open_vec_db(db_path: str | Path) -> sqlite3.Connection:
    """Open a sqlite connection with the sqlite-vec extension loaded.

    Uses the ``sqlite_vec`` pip module loader (present in the MacBook venv),
    not the system dylib path that ``pipeline/database.py`` uses.
    """
    conn = sqlite3.connect(str(db_path))
    if sqlite_vec is None:
        raise RuntimeError("sqlite-vec not installed; cannot create rescore table")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    # B2: this raw connection is the OTHER writer in the corruption scenario —
    # give it the same WAL + busy_timeout + synchronous as every other connection.
    from pipeline.database import apply_sqlite_pragmas

    apply_sqlite_pragmas(conn)
    return conn


def ensure_vec_table(conn: sqlite3.Connection) -> None:
    """Create the float rescore virtual table if missing.

    This is a NEW table ``vec_siglip_1152`` (float[1152], cosine). It does NOT
    reuse or alter the 768-dim ``vec_embeddings`` table owned by embedder.py.
    """
    conn.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS {VEC_TABLE} USING vec0(
            image_id INTEGER PRIMARY KEY,
            embedding float[{Tier1Embedder.EMBEDDING_DIM}] distance_metric=cosine
        )
        """
    )
    conn.commit()


def upsert_vec(conn: sqlite3.Connection, image_id: int, vector: np.ndarray) -> None:
    """Idempotent insert of one embedding into the float rescore table.

    vec0 rejects duplicate primary keys, so delete-then-insert keeps writes
    rerunnable (mirrors the on_conflict_do_nothing intent of Database.add_tags).
    """
    blob = serialize_float32(vector)
    conn.execute(f"DELETE FROM {VEC_TABLE} WHERE image_id = ?", (int(image_id),))
    conn.execute(
        f"INSERT INTO {VEC_TABLE} (image_id, embedding) VALUES (?, ?)",
        (int(image_id), blob),
    )


class Tier1Embedder:
    """SigLIP SO400M (dim 1152) -> turbovec ANN + sqlite-vec float rescore.

    Torch + transformers are imported lazily in ``_load`` — the MacBook venv
    lacks them, so the module and its pure-logic tests import cleanly there.
    """

    MODEL_ID = "google/siglip-so400m-patch14-384"
    EMBEDDING_DIM = 1152  # hidden_size of SO400M (NOT 768; embedder.py is stale)

    def __init__(self, index_path: str | Path = DEFAULT_INDEX_PATH) -> None:
        self.index_path = Path(index_path)
        self.processor: Any = None
        self.model: Any = None
        self.device: Any = None

    def _load(self) -> None:
        """Lazily import torch + transformers and load SigLIP onto mps-or-cpu."""
        if self.model is not None:
            return
        import torch  # lazy: MacBook venv has no torch
        from transformers import AutoModel, AutoProcessor

        self.device = (
            torch.device("mps")
            if torch.backends.mps.is_available()
            else torch.device("cpu")
        )
        logger.info("Loading %s on %s ...", self.MODEL_ID, self.device)
        self.processor = AutoProcessor.from_pretrained(self.MODEL_ID)
        self.model = AutoModel.from_pretrained(self.MODEL_ID).to(self.device).eval()

    def embed_image(self, rel_path: str) -> np.ndarray:
        """Embed one image (DB-relative path) -> L2-normalized float32[1152].

        Resolves the path via ``resolve_image_path`` (paths are RELATIVE to the
        content root). Reads ``get_image_features(...).pooler_output`` — the
        transformers 5.x ``BaseModelOutputWithPooling`` pooled vector.
        """
        import torch  # lazy

        self._load()
        path = resolve_image_path(rel_path)
        img = PILImage.open(path).convert("RGB")
        inputs = self.processor(images=img, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self.model.get_image_features(**inputs)
        pooled = out.pooler_output  # (1, 1152) — NOT bare tensor / last_hidden_state
        vec = pooled[0].detach().cpu().numpy().astype(np.float32)
        return l2_normalize(vec)

    def embed_images_batched(self, rel_paths: list[str]) -> np.ndarray:
        """Embed K images in one SigLIP forward -> L2-normalized float32[K, 1152].

        Numerically identical (within ~1e-4) to looping ``embed_image`` over the
        same paths, but a single batched forward starves the GPU far less. Row
        ``i`` of the returned matrix corresponds to ``rel_paths[i]`` — order is
        preserved end-to-end (load -> preprocess -> stack -> forward -> unstack).

        Reads ``get_image_features(...).pooler_output`` (the transformers 5.x
        ``BaseModelOutputWithPooling`` pooled vector) just like ``embed_image``.
        """
        import torch  # lazy

        self._load()
        if not rel_paths:
            return np.empty((0, self.EMBEDDING_DIM), dtype=np.float32)

        imgs = [PILImage.open(resolve_image_path(p)).convert("RGB") for p in rel_paths]
        # processor stacks the list into one [K, 3, 384, 384] pixel tensor,
        # preserving order; row i <-> imgs[i] <-> rel_paths[i].
        inputs = self.processor(images=imgs, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self.model.get_image_features(**inputs)
        pooled = out.pooler_output  # (K, 1152)
        mat = pooled.detach().cpu().numpy().astype(np.float32)
        # L2-normalize each row independently (per-row, matching embed_image).
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return (mat / norms).astype(np.float32)

    def embed_unprocessed(
        self,
        db: Any,
        limit: int = 100,
        db_path: str | Path | None = None,
        checkpoint_every: int = 200,
        batch_size: int = 16,
    ) -> int:
        """Embed DB image rows lacking a vector; write to BOTH stores.

        ``db`` is a ``pipeline.database.Database``. Iterates ``images`` rows not
        yet in the turbovec index, embeds them in chunks of ``batch_size`` via the
        batched SigLIP forward, and adds each result to the turbovec index and the
        ``vec_siglip_1152`` float table. Returns the number of images embedded.

        Batching only speeds the one-time embed pass; the stored vectors are the
        same (within ~1e-4) as the per-image path. ``batch_size`` defaults to 16
        and is halved on an MPS OOM (then retried), per the spec's memory budget.

        Every ``checkpoint_every`` embeddings the turbovec index is saved and the
        vec table committed, so a crash mid-pass keeps the work done so far (the
        .idx was previously written only once at the end → a crash lost it all).
        Checkpoints are also emitted after each batch once the cadence threshold
        is crossed, so partial progress survives even within a batch boundary.

        Resume semantics are unchanged: rows already in the turbovec index are
        skipped, so a re-run picks up exactly where a crash left off.

        Backup-before-write is the CALLER's job. This method only writes the
        index / vec table; it never migrates the main schema.
        """
        from pipeline.database import Image as ImageModel

        store = TurboVecStore(dim=self.EMBEDDING_DIM, bit_width=4, path=self.index_path)
        vec_db_path = db_path or db.db_path
        conn = open_vec_db(vec_db_path)
        ensure_vec_table(conn)

        embedded = 0
        last_checkpoint = 0
        try:
            with db.get_session() as session:
                rows = (
                    session.query(ImageModel.id, ImageModel.path)
                    .order_by(ImageModel.id)
                    .all()
                )
                # Skip rows already indexed (resume) and respect ``limit`` up front,
                # so the batched forward only ever sees work that still needs doing.
                pending: list[tuple[int, str]] = []
                for image_id, rel_path in rows:
                    if store.contains(image_id):
                        continue
                    pending.append((image_id, rel_path))
                    if len(pending) >= limit:
                        break

                for start in range(0, len(pending), batch_size):
                    chunk = pending[start : start + batch_size]
                    chunk_ids = [image_id for image_id, _ in chunk]
                    chunk_paths = [rel_path for _, rel_path in chunk]
                    try:
                        vecs = self._embed_batch_with_oom_retry(chunk_paths, batch_size)
                    except Exception as exc:  # pragma: no cover - per-batch I/O
                        logger.warning("embed failed for ids=%s: %s", chunk_ids, exc)
                        continue
                    # Row i <-> chunk_ids[i] <-> chunk_paths[i] (order preserved).
                    # Persist per-image so the checkpoint cadence (and crash
                    # resumability) is identical to the per-image path: a crash in
                    # the middle of a batch still leaves prior checkpoints on disk.
                    for image_id, vec in zip(chunk_ids, vecs):
                        store.add(image_id, vec)
                        upsert_vec(conn, image_id, vec)
                        embedded += 1
                        # B4: periodic checkpoint so a crash keeps prior work.
                        if embedded - last_checkpoint >= checkpoint_every:
                            store.save()
                            conn.commit()
                            last_checkpoint = embedded
                            logger.info("Tier-1 checkpoint at %d embedded", embedded)
            store.save()
            conn.commit()
        finally:
            conn.close()
        logger.info("Embedded %d images (Tier 1 SigLIP SO400M)", embedded)
        return embedded

    def _embed_batch_with_oom_retry(
        self, rel_paths: list[str], batch_size: int
    ) -> np.ndarray:
        """Embed a chunk, halving the batch and retrying on an MPS OOM.

        On an out-of-memory error the chunk is split in two and each half is
        embedded recursively (down to size 1). Rows are concatenated in order,
        so the returned matrix still maps row i -> rel_paths[i].
        """
        try:
            return self.embed_images_batched(rel_paths)
        except RuntimeError as exc:
            msg = str(exc).lower()
            is_oom = "out of memory" in msg or "mps" in msg and "memory" in msg
            if not is_oom or len(rel_paths) <= 1:
                raise
            half = max(1, len(rel_paths) // 2)
            logger.warning(
                "MPS OOM on batch of %d; halving to %d", len(rel_paths), half
            )
            left = self._embed_batch_with_oom_retry(rel_paths[:half], half)
            right = self._embed_batch_with_oom_retry(rel_paths[half:], half)
            return np.concatenate([left, right], axis=0)
