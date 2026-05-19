"""User management endpoints.

Covers the authenticated user's own profile (``/me``), admin-level CRUD for
all users, and avatar image upload/removal.

Role requirements:
    - ``GET /me`` — any authenticated user
    - ``GET /`` — ADMIN or MANAGER
    - ``POST /``, ``PUT /{id}``, ``DELETE /{id}`` — ADMIN only
    - ``POST /me/avatar``, ``DELETE /me/avatar`` — any authenticated user
"""

import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.roles import Role, require_roles
from app.crud.user import crud_user
from app.db.session import get_db
from app.dependencies import get_current_active_user
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate

#: Absolute path to the avatars directory on disk.
AVATARS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent.parent / "static" / "avatars"
)

#: MIME types accepted for avatar uploads.
ALLOWED_TYPES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif"}
)

#: Maximum avatar file size in bytes (3 MB).
MAX_AVATAR_SIZE: int = 3 * 1024 * 1024

router = APIRouter()


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_active_user)) -> User:
    """Return the profile of the currently authenticated user.

    Args:
        current_user: Authenticated user resolved by ``get_current_active_user``.

    Returns:
        The ``User`` ORM object serialised as ``UserResponse``.
    """
    return current_user


@router.get("/", response_model=List[UserResponse])
def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN, Role.MANAGER)),
) -> List[User]:
    """Return a paginated list of all users.

    Args:
        skip: Number of rows to skip (offset for pagination).
        limit: Maximum number of rows to return.
        db: Database session.
        _: Role guard — ADMIN or MANAGER only.

    Returns:
        A list of ``User`` objects serialised as ``UserResponse``.
    """
    return crud_user.get_all(db, skip=skip, limit=limit)


@router.post("/", response_model=UserResponse)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
) -> User:
    """Create a new user account.

    Args:
        user_in: Validated ``UserCreate`` payload (includes plain-text password).
        db: Database session.
        _: Role guard — ADMIN only.

    Returns:
        The newly created ``User`` object.

    Raises:
        HTTPException 400: If the username is already taken.
    """
    existing = crud_user.get_by_username(db, user_in.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )
    return crud_user.create(db, user_in)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
) -> User:
    """Partially update a user's profile fields.

    Only fields included in *user_in* are changed (``exclude_unset=True``).

    Args:
        user_id: Primary key of the user to update.
        user_in: ``UserUpdate`` schema with the fields to change.
        db: Database session.
        _: Role guard — ADMIN only.

    Returns:
        The updated ``User`` object.

    Raises:
        HTTPException 404: If no user exists with *user_id*.
    """
    user = crud_user.update(db, user_id, user_in)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
) -> None:
    """Permanently delete a user account.

    Args:
        user_id: Primary key of the user to delete.
        db: Database session.
        _: Role guard — ADMIN only.

    Raises:
        HTTPException 404: If no user exists with *user_id*.
    """
    user = crud_user.get(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    crud_user.delete(db, user_id)


@router.post("/me/avatar", response_model=UserResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> User:
    """Replace the current user's avatar image.

    Validates MIME type and file size, generates a UUID-based filename to
    prevent path-traversal attacks, deletes the previous avatar if one exists,
    and saves the new file to ``AVATARS_DIR``.

    Args:
        file: Uploaded image file from the multipart form.
        current_user: Authenticated user whose avatar is being updated.
        db: Database session.

    Returns:
        The updated ``User`` object with the new ``avatar_url``.

    Raises:
        HTTPException 400: If the MIME type is not in ``ALLOWED_TYPES`` or the
            file exceeds ``MAX_AVATAR_SIZE``.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG, PNG, WebP or GIF images are allowed.",
        )

    contents = await file.read()
    if len(contents) > MAX_AVATAR_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image must be smaller than 3 MB.",
        )

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    filename = f"user_{current_user.id}_{uuid.uuid4().hex[:8]}.{ext}"
    save_path = AVATARS_DIR / filename
    AVATARS_DIR.mkdir(parents=True, exist_ok=True)

    if current_user.avatar_url:
        old_file = AVATARS_DIR / Path(current_user.avatar_url).name
        if old_file.exists():
            old_file.unlink(missing_ok=True)

    save_path.write_bytes(contents)

    current_user.avatar_url = f"/static/avatars/{filename}"
    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/me/avatar", response_model=UserResponse)
def remove_avatar(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> User:
    """Remove the current user's avatar image.

    Deletes the file from disk and clears ``avatar_url`` in the database.
    A no-op if the user has no avatar.

    Args:
        current_user: Authenticated user whose avatar is being removed.
        db: Database session.

    Returns:
        The updated ``User`` object with ``avatar_url`` set to ``None``.
    """
    if current_user.avatar_url:
        old_file = AVATARS_DIR / Path(current_user.avatar_url).name
        if old_file.exists():
            old_file.unlink(missing_ok=True)
        current_user.avatar_url = None
        db.commit()
        db.refresh(current_user)
    return current_user
