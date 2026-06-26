"""
Lane D — personalization (rungs 1-2) + licensing scaffold tests.

Pure-numpy probe logic, the active-learning ranking over a FRESH TEMP sqlite db,
and the offline licensing scaffold. NO torch, NO model load, NO network, and the
temp-db tests NEVER touch the real ``data/catalog.db`` — they build their own
sqlite file under ``tmp_path``. Heavy/optional deps (sqlite-vec extension) are
``skipif``-guarded.

Mirrors ``tests/test_self_retrieval.py``: insert the repo root onto sys.path at
the top so the worktree's code is used, not any installed copy.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.licensing import (  # noqa: E402
    LicenseStatus,
    ProFeature,
    Tier,
    feature_enabled,
    load_license,
    parse_token,
)
from pipeline.personalize import active_learning, probe  # noqa: E402


# --------------------------------------------------------------------------- #
# Probe (rung 1) — pure numpy, no db.                                          #
# --------------------------------------------------------------------------- #
def _two_clusters(dim: int = 1152, n: int = 30, seed: int = 0):
    """Two linearly separable unit-norm clusters in opposite directions."""
    rng = np.random.default_rng(seed)
    base = rng.standard_normal(dim).astype(np.float32)
    base /= np.linalg.norm(base)
    pos = base[None, :] + 0.05 * rng.standard_normal((n, dim)).astype(np.float32)
    neg = -base[None, :] + 0.05 * rng.standard_normal((n, dim)).astype(np.float32)
    pos /= np.linalg.norm(pos, axis=1, keepdims=True)
    neg /= np.linalg.norm(neg, axis=1, keepdims=True)
    return pos.astype(np.float32), neg.astype(np.float32)


def test_probe_separates_two_clusters():
    pos, neg = _two_clusters()
    p = probe.fit_linear_probe(pos, neg)
    # Positives score well above 0.5, negatives well below.
    assert p.score(pos).mean() > 0.9
    assert p.score(neg).mean() < 0.1
    # Margin sign tracks the class.
    assert (p.margin(pos) > 0).all()
    assert (p.margin(neg) < 0).all()


def test_probe_score_in_unit_interval():
    pos, neg = _two_clusters()
    p = probe.fit_linear_probe(pos, neg)
    s = p.score(np.vstack([pos, neg]))
    assert s.min() >= 0.0 and s.max() <= 1.0


def test_probe_empty_positive_raises():
    _, neg = _two_clusters()
    with pytest.raises(ValueError):
        probe.fit_linear_probe(np.empty((0, 1152), dtype=np.float32), neg)


def test_probe_empty_negative_raises():
    pos, _ = _two_clusters()
    with pytest.raises(ValueError):
        probe.fit_linear_probe(pos, np.empty((0, 1152), dtype=np.float32))


def test_probe_dim_mismatch_raises():
    pos, _ = _two_clusters(dim=1152)
    neg, _ = _two_clusters(dim=768)
    with pytest.raises(ValueError):
        probe.fit_linear_probe(pos, neg)


# --------------------------------------------------------------------------- #
# Licensing scaffold — offline, fail-safe, no content gate.                   #
# --------------------------------------------------------------------------- #
def test_no_token_is_community(monkeypatch, tmp_path):
    monkeypatch.delenv("MEDIA_PIPELINE_LICENSE", raising=False)
    st = load_license(project_root=tmp_path)
    assert st.tier is Tier.COMMUNITY
    assert not st.has(ProFeature.BULK_EXPORT)


def _signed_pro_token(monkeypatch):
    """Mint a real Ed25519-signed pro token against an ephemeral baked-in key.

    Updated for Spec I: ``parse_token`` now does real signature verification, so a
    bare ``MPL-PRO-x`` string is (correctly) rejected. These tests sign a genuine
    token rather than asserting the old forgeable shape-check.
    """
    import time

    from pipeline import license_tokens as lt
    from pipeline.license_tokens import (
        LicenseClaims,
        generate_keypair,
        load_private_key_b64,
        sign_token,
    )
    from pipeline.licensing import APP_MAJOR_VERSION

    priv_b64, pub_b64 = generate_keypair()
    monkeypatch.setattr(lt, "PUBLIC_KEY_B64", pub_b64)
    claims = LicenseClaims(
        tier="pro", max_version=APP_MAJOR_VERSION, issued_at=int(time.time())
    )
    return sign_token(claims, load_private_key_b64(priv_b64))


def test_valid_pro_token_unlocks_features(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_PIPELINE_LICENSE", _signed_pro_token(monkeypatch))
    st = load_license(project_root=tmp_path)
    assert st.tier is Tier.PRO
    assert st.has(ProFeature.REMOTE_COMPUTE_ROUTING)
    assert feature_enabled(ProFeature.BULK_EXPORT, status=st)


def test_malformed_token_fails_safe():
    assert parse_token("garbage") is Tier.COMMUNITY
    assert parse_token("MPL-PRO") is Tier.COMMUNITY  # missing opaque segment
    assert parse_token("MPL-PRO-") is Tier.COMMUNITY  # empty opaque
    assert parse_token("XXX-PRO-abc") is Tier.COMMUNITY  # wrong prefix
    assert parse_token("") is Tier.COMMUNITY
    assert parse_token(None) is Tier.COMMUNITY


def test_pro_token_via_key_file(monkeypatch, tmp_path):
    monkeypatch.delenv("MEDIA_PIPELINE_LICENSE", raising=False)
    token = _signed_pro_token(monkeypatch)
    (tmp_path / "license.key").write_text(token + "\n", encoding="utf-8")
    st = load_license(project_root=tmp_path)
    assert st.tier is Tier.PRO


def test_pro_only_feature_gated_without_license():
    # All declared ProFeatures are pro-only; community status must NOT enable them.
    community = LicenseStatus()
    assert not feature_enabled(ProFeature.PRIORITY_SUPPORT, status=community)


# --------------------------------------------------------------------------- #
# Active-learning (rung 2) over a FRESH TEMP db (never the real catalog.db).   #
# --------------------------------------------------------------------------- #
def _sqlite_vec_available() -> bool:
    try:
        from pipeline.tier1_embedder import open_vec_db  # noqa: F401
    except Exception:
        return False
    import tempfile

    path = Path(tempfile.mkdtemp()) / "probe.db"
    try:
        conn = open_vec_db(path)
        conn.execute("SELECT vec_version()")
        conn.close()
        return True
    except Exception:
        return False


vec_skip = pytest.mark.skipif(
    not _sqlite_vec_available(), reason="sqlite-vec extension not loadable"
)


def _seed_temp_db(tmp_path):
    """Build a fresh temp catalog.db with images + vectors. Returns Database."""
    from pipeline.database import Database
    from pipeline.tier1_embedder import (
        ensure_vec_table,
        open_vec_db,
        serialize_float32,
    )

    db_path = tmp_path / "catalog.db"
    db = Database(str(db_path))

    pos, neg = _two_clusters(n=10, seed=1)
    # Build clearly-positive, clearly-negative, and ambiguous (boundary) vectors.
    boundary = (pos[0] + neg[0]) / 2.0
    boundary /= np.linalg.norm(boundary)

    rows = []  # (image_id, flag_action, vector)
    iid = 1
    for v in pos:
        rows.append((iid, "keep", v))
        iid += 1
    for v in neg:
        rows.append((iid, "reject", v))
        iid += 1
    # Unlabeled pool: one near-positive, one near-negative, one at the boundary.
    unlabeled = [
        (iid, None, pos[1]),
        (iid + 1, None, neg[1]),
        (iid + 2, "maybe", boundary.astype(np.float32)),
    ]
    rows.extend(unlabeled)

    from pipeline.database import Image

    with db.get_session() as session:
        for image_id, action, _ in rows:
            session.add(
                Image(
                    id=image_id,
                    path=f"library/test/unrated/{image_id:012d}.jpg",
                    file_hash=f"hash{image_id:060d}",
                    flag_action=action,
                    flagged=action is not None,
                )
            )
        session.commit()

    conn = open_vec_db(db_path)
    try:
        ensure_vec_table(conn)
        for image_id, _, v in rows:
            conn.execute(
                "INSERT INTO vec_siglip_1152 (image_id, embedding) VALUES (?, ?)",
                (int(image_id), serialize_float32(np.asarray(v, dtype=np.float32))),
            )
        conn.commit()
    finally:
        conn.close()

    return db, [r[0] for r in unlabeled]


@vec_skip
def test_load_flag_labels_partitions(tmp_path):
    db, unlabeled_ids = _seed_temp_db(tmp_path)
    pos, neg, unlabeled = active_learning.load_flag_labels(db)
    assert len(pos) == 10
    assert len(neg) == 10
    # NULL + 'maybe' both land in the unlabeled pool.
    assert set(unlabeled) == set(unlabeled_ids)


@vec_skip
def test_propose_next_ranks_by_uncertainty(tmp_path):
    db, unlabeled_ids = _seed_temp_db(tmp_path)
    result = active_learning.propose_next(db, count=3)
    assert result["ready"] is True
    assert result["n_pos"] == 10 and result["n_neg"] == 10
    proposals = result["proposals"]
    assert proposals, "expected proposals"
    # Every proposal is drawn from the unlabeled pool.
    assert all(p["image_id"] in set(unlabeled_ids) for p in proposals)
    # The boundary image (id = max unlabeled) is the most uncertain -> ranked first.
    boundary_id = max(unlabeled_ids)
    assert proposals[0]["image_id"] == boundary_id
    # Uncertainty ordering: |margin| non-decreasing.
    margins = [abs(p["margin"]) for p in proposals]
    assert margins == sorted(margins)


@vec_skip
def test_propose_next_cold_start_no_negatives(tmp_path):
    """With keeps but no rejects, falls back (ready=False) but still proposes."""
    from pipeline.database import Database, Image
    from pipeline.tier1_embedder import (
        ensure_vec_table,
        open_vec_db,
        serialize_float32,
    )

    db_path = tmp_path / "catalog.db"
    db = Database(str(db_path))
    pos, _ = _two_clusters(n=5, seed=2)
    with db.get_session() as session:
        for i, _v in enumerate(pos, start=1):
            session.add(
                Image(
                    id=i,
                    path=f"library/t/unrated/{i:012d}.jpg",
                    file_hash=f"h{i:063d}",
                    flag_action="keep" if i <= 3 else None,
                )
            )
        session.commit()
    conn = open_vec_db(db_path)
    try:
        ensure_vec_table(conn)
        for i, v in enumerate(pos, start=1):
            conn.execute(
                "INSERT INTO vec_siglip_1152 (image_id, embedding) VALUES (?, ?)",
                (i, serialize_float32(np.asarray(v, dtype=np.float32))),
            )
        conn.commit()
    finally:
        conn.close()

    result = active_learning.propose_next(db, count=5)
    assert result["ready"] is False
    assert result["n_neg"] == 0
    assert result["proposals"]  # cold-start similarity fallback still ranks
