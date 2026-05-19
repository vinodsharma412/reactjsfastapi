"""SQLAlchemy declarative base shared by all ORM models.

Every model class must inherit from ``Base`` so that
``Base.metadata.create_all()`` can discover and create its table.
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()
