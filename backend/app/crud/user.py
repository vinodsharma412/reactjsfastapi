"""User-specific CRUD operations.

Extends ``CRUDBase[User]`` with lookup-by-username/email, creation with
password hashing, and a partial-update method that only touches supplied fields.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.crud.base import CRUDBase
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


class CRUDUser(CRUDBase[User]):
    """Repository for the ``users`` table."""

    def get_by_username(self, db: Session, username: str) -> Optional[User]:
        """Look up a user by their unique username.

        Args:
            db: Active database session.
            username: Exact username string to search for.

        Returns:
            The matching ``User`` ORM object, or ``None``.
        """
        return db.query(User).filter(User.username == username).first()

    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        """Look up a user by their unique email address.

        Args:
            db: Active database session.
            email: Exact email string to search for.

        Returns:
            The matching ``User`` ORM object, or ``None``.
        """
        return db.query(User).filter(User.email == email).first()

    def create(self, db: Session, user_in: UserCreate) -> User:
        """Create a new user row with a hashed password.

        Args:
            db: Active database session.
            user_in: Validated ``UserCreate`` schema (contains plain-text password).

        Returns:
            The newly created and refreshed ``User`` ORM object.
        """
        user = User(
            username=user_in.username,
            email=user_in.email,
            full_name=user_in.full_name,
            role=user_in.role,
            hashed_password=hash_password(user_in.password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def update(self, db: Session, user_id: int, user_in: UserUpdate) -> Optional[User]:
        """Partially update a user — only fields present in *user_in* are changed.

        ``exclude_unset=True`` ensures that omitted optional fields are not
        overwritten with their default values.  If ``"password"`` is supplied it
        is hashed before storage and the plain-text key is removed.

        Args:
            db: Active database session.
            user_id: Primary key of the user to update.
            user_in: ``UserUpdate`` schema; only set fields are applied.

        Returns:
            The updated ``User`` ORM object, or ``None`` if not found.
        """
        user = self.get(db, user_id)
        if not user:
            return None
        update_data = user_in.dict(exclude_unset=True)
        if "password" in update_data:
            update_data["hashed_password"] = hash_password(update_data.pop("password"))
        for field, value in update_data.items():
            setattr(user, field, value)
        db.commit()
        db.refresh(user)
        return user


crud_user = CRUDUser(User)
