import sqlite3
from pathlib import Path

import pytest

from pipeline.labels.store import LabelStore
from pipeline.migrations import apply_migration

MIG = Path("data/migrations/013_label_sets.sql")


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE images (id INTEGER PRIMARY KEY, rating TEXT);
        CREATE TABLE user_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_id INTEGER NOT NULL, category TEXT NOT NULL, value TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')), owner_id INTEGER,
            UNIQUE(image_id, category, value)
        );
        INSERT INTO images (id, rating) VALUES (1, NULL);
        """
    )
    conn.commit()
    apply_migration(conn, MIG)
    conn.close()
    return LabelStore(db)


def test_backfill_count_equals_non_unrated_with_legacy_collision(tmp_path):
    """The Rating backfill must not silently drop images whose legacy rating row
    (category='rating', set_id=NULL) collides with the inherited table-level
    UNIQUE. Post-migration set_id=1 rows must equal the non-unrated image count."""
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE images (id INTEGER PRIMARY KEY, rating TEXT);
        CREATE TABLE user_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_id INTEGER NOT NULL, category TEXT NOT NULL, value TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')), owner_id INTEGER,
            UNIQUE(image_id, category, value)
        );
        INSERT INTO images (id, rating) VALUES (1, 'sfw'), (2, 'nsfw'),
            (3, 'suggestive'), (4, 'unrated'), (5, NULL);
        -- pre-existing legacy rating rows (set_id NULL) that collide with backfill
        INSERT INTO user_labels (image_id, category, value, owner_id) VALUES
            (3, 'rating', 'suggestive', 1),
            (1, 'rating', 'sfw', 1);
        """
    )
    conn.commit()
    apply_migration(conn, MIG)
    expected = conn.execute(
        "SELECT COUNT(*) FROM images WHERE rating IS NOT NULL AND rating <> 'unrated'"
    ).fetchone()[0]
    got = conn.execute("SELECT COUNT(*) FROM user_labels WHERE set_id = 1").fetchone()[
        0
    ]
    conn.close()
    assert expected == 3
    assert got == expected  # no image dropped by the legacy UNIQUE collision


def test_seeded_rating_set_is_listed(store):
    sets = store.list_sets()
    rating = next(s for s in sets if s["name"] == "Rating")
    assert rating["single_select"] == 1
    assert {v["value"] for v in rating["values"]} == {
        "unrated",
        "sfw",
        "suggestive",
        "nsfw",
    }


def test_create_set_and_add_values(store):
    sid = store.create_set("Project", single_select=False, color="#62b8dc")
    store.add_value(sid, "alpha")
    store.add_value(sid, "beta")
    assert store.add_value(sid, "alpha") == store.add_value(sid, "alpha")  # idempotent
    proj = next(s for s in store.list_sets() if s["id"] == sid)
    assert {v["value"] for v in proj["values"]} == {"alpha", "beta"}


def test_single_select_replaces(store):
    store.assign_label(1, 1, "sfw")
    store.assign_label(1, 1, "nsfw")  # same single-select set -> replaces
    labels = [lbl for lbl in store.labels_for_image(1) if lbl["set_id"] == 1]
    assert len(labels) == 1
    assert labels[0]["value"] == "nsfw"


def test_multi_select_accumulates(store):
    sid = store.create_set("Mood", single_select=False)
    store.add_value(sid, "calm")
    store.add_value(sid, "tense")
    store.assign_label(1, sid, "calm")
    store.assign_label(1, sid, "tense")
    vals = {lbl["value"] for lbl in store.labels_for_image(1) if lbl["set_id"] == sid}
    assert vals == {"calm", "tense"}


def test_assign_label_adopts_legacy_set_id_null_row(tmp_path):
    """A legacy row (image_id, category='Rating', value, set_id=NULL) must not
    crash assign_label: the inherited table-level UNIQUE(image_id, category,
    value) makes the INSERT OR IGNORE a no-op, so the store must adopt the
    existing row into the set instead of raising TypeError (HTTP 500)."""
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE images (id INTEGER PRIMARY KEY, rating TEXT);
        CREATE TABLE user_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_id INTEGER NOT NULL, category TEXT NOT NULL, value TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')), owner_id INTEGER,
            UNIQUE(image_id, category, value)
        );
        INSERT INTO images (id, rating) VALUES (1, NULL);
        -- legacy row with set_id absent (NULL after the ALTER), category matches
        -- the Rating set name that assign_label writes.
        INSERT INTO user_labels (image_id, category, value, owner_id)
        VALUES (1, 'Rating', 'sfw', 1);
        """
    )
    conn.commit()
    apply_migration(conn, MIG)
    conn.close()
    store = LabelStore(db)

    lid = store.assign_label(1, 1, "sfw")
    assert isinstance(lid, int)
    labels = [lbl for lbl in store.labels_for_image(1) if lbl["set_id"] == 1]
    assert len(labels) == 1
    assert labels[0]["value"] == "sfw"


def test_update_set_rename_recolor_single_select(store):
    sid = store.create_set("Project", single_select=False, color="#111111")
    store.update_set(sid, name="Status", single_select=True, color="#222222")
    s = next(x for x in store.list_sets() if x["id"] == sid)
    assert s["name"] == "Status"
    assert s["single_select"] == 1
    assert s["color"] == "#222222"


def test_update_set_reorder_changes_list_order(store):
    store.create_set("Aaa")
    b = store.create_set("Bbb")
    # Push Bbb before Aaa via sort_order; list_sets orders by sort_order, id.
    store.update_set(b, sort_order=-1)
    order = [s["name"] for s in store.list_sets()]
    assert order.index("Bbb") < order.index("Aaa")


def test_update_set_partial_leaves_other_fields(store):
    sid = store.create_set("Keep", single_select=True, color="#abcabc")
    store.update_set(sid, name="Kept")  # only rename
    s = next(x for x in store.list_sets() if x["id"] == sid)
    assert s["name"] == "Kept"
    assert s["single_select"] == 1  # unchanged
    assert s["color"] == "#abcabc"  # unchanged


def test_remove_value_drops_definition_but_keeps_assignment(store):
    """remove_value deletes the label_definitions row only (store.py:127).

    The contract is a bare ``DELETE FROM label_definitions WHERE id = ?`` — it
    does NOT cascade into user_labels, so an already-assigned label that
    references that value survives (the value definition disappears from
    list_sets, but the assignment row remains). Asserts both halves.
    """
    sid = store.create_set("Project", single_select=False)
    vid_a = store.add_value(sid, "alpha")
    store.add_value(sid, "beta")
    store.assign_label(1, sid, "alpha")  # assignment referencing the value

    store.remove_value(vid_a)

    # The value definition is gone from the set.
    proj = next(s for s in store.list_sets() if s["id"] == sid)
    assert {v["value"] for v in proj["values"]} == {"beta"}
    # The existing assignment is untouched (no cascade by contract).
    assigned = [lbl for lbl in store.labels_for_image(1) if lbl["set_id"] == sid]
    assert [lbl["value"] for lbl in assigned] == ["alpha"]


def test_unassign_and_delete_set(store):
    lid = store.assign_label(1, 1, "sfw")
    store.unassign(lid)
    assert [lbl for lbl in store.labels_for_image(1) if lbl["set_id"] == 1] == []
    sid = store.create_set("Temp")
    store.add_value(sid, "x")
    store.assign_label(1, sid, "x")
    store.delete_set(sid)
    assert all(s["id"] != sid for s in store.list_sets())
    assert [lbl for lbl in store.labels_for_image(1) if lbl["set_id"] == sid] == []
