"""
Smoke tests for pipeline/database.py — Image CRUD, Tags, Grids.
"""

from pipeline.database import Tag


class TestDatabaseInit:
    """Database initialization and connection."""

    def test_init_creates_db_file(self, db):
        """New DB file should exist after Database() init."""
        assert db.db_path is not None

    def test_get_session_yields_session(self, db):
        """get_session() should yield an active SQLAlchemy session."""
        with db.get_session() as session:
            assert session is not None


class TestImageOperations:
    """Image CRUD: add, query, duplicate handling."""

    def test_add_image_returns_instance(self, db, session, sample_image_data):
        """Valid image_data → Image instance with auto-assigned ID."""
        img = db.add_image(session, sample_image_data)
        session.commit()
        assert img is not None
        assert img.id is not None
        assert img.file_hash == sample_image_data["file_hash"]

    def test_add_image_duplicate_hash_skips(self, db, session, sample_image_data):
        """Same file_hash → returns existing, doesn't create duplicate."""
        first = db.add_image(session, sample_image_data)
        session.commit()
        second = db.add_image(session, sample_image_data)
        session.commit()
        assert first.id == second.id

    def test_add_tags_persists(self, db, session, sample_image_data):
        """After add_tags, tags are persisted in the database."""
        img = db.add_image(session, sample_image_data)
        session.commit()
        tags = {
            "clothing": ["t-shirt"],
            "rating": ["sfw"],
        }
        db.add_tags(session, img.id, tags)
        session.commit()
        # Tags should be persisted
        tag_count = session.query(Tag).filter(Tag.image_id == img.id).count()
        assert tag_count == 2
        # Verify tag values
        tag_values = session.query(Tag.value).filter(Tag.image_id == img.id).all()
        assert "t-shirt" in [t[0] for t in tag_values]
        assert "sfw" in [t[0] for t in tag_values]

    def test_search_by_tags_no_results(self, db, session):
        """Filter with no matches → empty list."""
        results = db.search_by_tags(session, {"category": "nonexistent"})
        assert len(results) == 0


class TestGridPersistence:
    """Grid creation and storage."""

    def test_create_grid_persists(self, db, session, sample_image_data):
        """Grid saved to DB with correct data."""
        img = db.add_image(session, sample_image_data)
        session.commit()
        grid = db.create_grid(
            session=session,
            name="test-grid",
            description="test",
            layout="2x2",
            image_ids=[img.id],
        )
        session.commit()
        assert grid is not None
        assert grid.name == "test-grid"
        assert grid.layout == "2x2"
