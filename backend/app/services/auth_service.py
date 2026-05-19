"""Authentication business logic.

Separates auth logic from the HTTP layer so it can be tested without
a live request context. The endpoint calls ``login_user`` and receives a
ready-to-return JWT string.
"""

from sqlalchemy.orm import Session

from app.core.exceptions import inactive_user_exception, invalid_credentials_exception
from app.core.security import create_access_token, verify_password
from app.crud.user import crud_user


def login_user(db: Session, username: str, password: str) -> str:
    """Validate credentials and return a signed JWT access token.

    Raises specific ``HTTPException`` instances so the caller (the auth endpoint)
    can propagate them directly to the HTTP response without extra logic.

    Args:
        db: Active database session used to look up the user.
        username: Username submitted in the login form.
        password: Plain-text password submitted in the login form.

    Returns:
        A compact JWT string to be returned as ``access_token`` in the response.

    Raises:
        HTTPException 401: If the username does not exist or the password is wrong.
        HTTPException 400: If the user account is inactive.
    """
    user = crud_user.get_by_username(db, username)
    if not user or not verify_password(password, user.hashed_password):
        raise invalid_credentials_exception
    if not user.is_active:
        raise inactive_user_exception
    return create_access_token({"sub": user.username})
