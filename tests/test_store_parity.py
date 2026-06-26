"""Tests for the Tier-1 store row-parity gate (validate_h100_parity).

Builds a tiny temp sqlite with a stub ``vec_siglip_1152`` table and monkeypatches
the turbovec ``.idx`` loader so its row count can be made to match or mismatch the
table. Parity must pass only when vec table == idx == imported ids, all non-zero.
"""

from __future__ import annotations

import sqlite3

import pytest

from scripts import validate_h100_parity as vp


class _StubIdx:
    def __init__(self, n: int) -> None:
        self._n = n

    def __len__(self) -> int:
        return self._n


def _make_db(tmp_path, n_rows: int):
    db_path = tmp_path / "catalog.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        f"CREATE TABLE {vp_vec_table()} (image_id INTEGER PRIMARY KEY, embedding BLOB)"
    )
    for i in range(1, n_rows + 1):
        conn.execute(
            f"INSERT INTO {vp_vec_table()} (image_id, embedding) VALUES (?, ?)",
            (i, b"x"),
        )
    conn.commit()
    conn.close()
    return db_path


def vp_vec_table() -> str:
    from pipeline.tier1_embedder import VEC_TABLE

    return VEC_TABLE


def _patch_idx(monkeypatch, n_rows: int) -> None:
    import turbovec

    monkeypatch.setattr(
        turbovec.IdMapIndex,
        "load",
        staticmethod(lambda _path: _StubIdx(n_rows)),
    )


def test_parity_passes_when_counts_match(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path, 5)
    _patch_idx(monkeypatch, 5)
    rep = vp.validate_store_parity(db_path)
    assert rep["pass"] is True
    assert rep["vec_siglip_1152"] == rep["idx_rows"] == rep["imported_ids"] == 5
    assert vp.run_store_parity(db_path) == 0


def test_parity_fails_on_idx_skew(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path, 5)
    _patch_idx(monkeypatch, 4)  # idx short by one
    rep = vp.validate_store_parity(db_path)
    assert rep["pass"] is False
    assert rep["idx_rows"] == 4
    assert vp.run_store_parity(db_path) == 1


def test_parity_fails_when_empty(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path, 0)
    _patch_idx(monkeypatch, 0)
    rep = vp.validate_store_parity(db_path)
    # All three agree at 0 but parity requires non-zero.
    assert rep["pass"] is False
    assert vp.run_store_parity(db_path) == 1


def test_cli_check_store_parity(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path, 3)
    _patch_idx(monkeypatch, 3)
    assert vp.main(["--check-store-parity", "--db", str(db_path)]) == 0

    _patch_idx(monkeypatch, 2)
    assert vp.main(["--check-store-parity", "--db", str(db_path)]) == 1


def test_tier_mode_requires_artifact_args():
    # Without --check-store-parity the tier args are mandatory.
    with pytest.raises(SystemExit):
        vp.main(["--tiers", "0"])
