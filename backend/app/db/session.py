"""Database engine and session factory.

``engine`` is created once at import time and reused for the lifetime of the
process. ``SessionLocal`` is a factory; call it to obtain a new ``Session``.
``get_db`` is the FastAPI dependency that yields a session per request.
"""

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for the duration of a single request.

    Designed for use with FastAPI's ``Depends()``::

        @router.get("/users")
        def list_users(db: Session = Depends(get_db)):
            ...

    The session is always closed in the ``finally`` block even if the
    endpoint raises an exception, preventing connection leaks.

    Yields:
        An active ``sqlalchemy.orm.Session`` bound to the application engine.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
