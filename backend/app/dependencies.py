"""FastAPI dependency graph for authentication.

Provides two chained dependencies:

* ``get_current_user`` — decodes the JWT and fetches the matching User row.
* ``get_current_active_user`` — additionally asserts the account is active.

Endpoints import these via ``Depends()``; ``require_roles`` in ``core/roles.py``
builds on top of ``get_current_active_user``.
"""

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.exceptions import credentials_exception
from app.core.security import decode_token
from app.crud.user import crud_user
from app.db.session import get_db
from app.models.user import User

#: Tells FastAPI where the client can obtain a token (shown in OpenAPI docs).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Decode the Bearer JWT and return the corresponding ``User``.

    Args:
        token: JWT extracted from the ``Authorization: Bearer <token>`` header
            by ``OAuth2PasswordBearer``.
        db: Database session injected by ``get_db``.

    Returns:
        The ``User`` ORM object whose username matches the ``sub`` claim.

    Raises:
        HTTPException 401: If the token is invalid, expired, missing the
            ``sub`` claim, or the username has no matching row in the DB.
    """
    try:
        payload = decode_token(token)
        username: str = payload.get("sub")
        if not username:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = crud_user.get_by_username(db, username)
    if not user:
        raise credentials_exception
    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Assert the authenticated user's account is active.

    Chains on top of ``get_current_user`` — FastAPI resolves ``get_current_user``
    first and passes its result here.

    Args:
        current_user: Authenticated ``User`` resolved by ``get_current_user``.

    Returns:
        The same ``User`` object, confirmed active.

    Raises:
        HTTPException 401: If ``user.is_active`` is ``False``.
    """
    if not current_user.is_active:
        raise credentials_exception
    return current_user
