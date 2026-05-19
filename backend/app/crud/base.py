"""Generic CRUD base class (Repository pattern).

``CRUDBase[ModelType]`` provides typed ``get``, ``get_all``, and ``delete``
operations for any SQLAlchemy model. Domain-specific CRUD classes subclass it
and add their own methods (create, update, etc.).
"""

from typing import Generic, List, Optional, Type, TypeVar

from sqlalchemy.orm import Session

ModelType = TypeVar("ModelType")


class CRUDBase(Generic[ModelType]):
    """Repository base providing common DB read/delete operations.

    Args:
        model: The SQLAlchemy ORM model class (e.g. ``User``, ``Stock``).

    Example::

        class CRUDUser(CRUDBase[User]):
            def get_by_username(self, db, username): ...

        crud_user = CRUDUser(User)
    """

    def __init__(self, model: Type[ModelType]) -> None:
        self.model = model

    def get(self, db: Session, id: int) -> Optional[ModelType]:
        """Fetch a single record by primary key.

        Args:
            db: Active database session.
            id: Primary-key value to look up.

        Returns:
            The matching ORM object, or ``None`` if not found.
        """
        return db.query(self.model).filter(self.model.id == id).first()

    def get_all(
        self, db: Session, skip: int = 0, limit: int = 100
    ) -> List[ModelType]:
        """Return a paginated list of records.

        Args:
            db: Active database session.
            skip: Number of rows to skip (offset).
            limit: Maximum number of rows to return.

        Returns:
            A list of ORM objects (may be empty).
        """
        return db.query(self.model).offset(skip).limit(limit).all()

    def delete(self, db: Session, id: int) -> Optional[ModelType]:
        """Delete a record by primary key and commit the transaction.

        Args:
            db: Active database session.
            id: Primary-key of the record to delete.

        Returns:
            The deleted ORM object, or ``None`` if the record did not exist.
        """
        obj = self.get(db, id)
        if obj:
            db.delete(obj)
            db.commit()
        return obj
