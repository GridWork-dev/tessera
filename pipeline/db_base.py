"""SQLAlchemy declarative base for the media pipeline.

Split out of ``pipeline.database`` so the ORM models (``pipeline.models``) and
the connection/helper layer (``pipeline.database``) can share one ``Base``
without a circular import. ``pipeline.database`` re-exports ``Base`` so existing
``from pipeline.database import Base`` continues to work unchanged.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base (replaces deprecated declarative_base())."""
