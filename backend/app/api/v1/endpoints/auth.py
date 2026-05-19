"""Authentication endpoints.

Provides the OAuth2 password-grant token endpoint consumed by the frontend
login form and the OpenAPI "Authorize" button.
"""

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import Token
from app.services.auth_service import login_user

router = APIRouter()


@router.post("/token", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """Exchange username + password for a JWT access token.

    The request body must be ``application/x-www-form-urlencoded`` (OAuth2
    convention), not JSON.  The frontend sends it via ``URLSearchParams``.

    Args:
        form_data: Username and password parsed from the form body by FastAPI.
        db: Database session injected by ``get_db``.

    Returns:
        A ``Token`` schema with ``access_token`` (JWT) and ``token_type``
        (always ``"bearer"``).

    Raises:
        HTTPException 401: If credentials are invalid (delegated to
            ``login_user``).
        HTTPException 400: If the user account is inactive.
    """
    token = login_user(db, form_data.username, form_data.password)
    return {"access_token": token, "token_type": "bearer"}
