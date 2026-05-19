"""Role-based access control (RBAC) helpers.

Defines the ``Role`` enum and the ``require_roles`` factory that produces
FastAPI dependency checkers for endpoint-level authorisation.
"""

from enum import Enum

from fastapi import Depends, HTTPException, status

from app.models.user import User


class Role(str, Enum):
    """Application-level user roles.

    Values are stored as plain strings in the ``users.role`` column, so
    ``str`` is used as the mixin base to allow direct comparison with DB values.
    """

    ADMIN = "admin"
    MANAGER = "manager"
    VIEWER = "viewer"


def require_roles(*roles: Role):
    """Factory that returns a FastAPI dependency enforcing role membership.

    Usage::

        @router.delete("/users/{id}")
        def delete_user(user=Depends(require_roles(Role.ADMIN))):
            ...

    Args:
        *roles: One or more ``Role`` enum values that are permitted to call
            the decorated endpoint.

    Returns:
        A FastAPI-compatible dependency function that raises
        ``HTTP 403 Forbidden`` if the authenticated user's role is not in
        *roles*, or returns the ``User`` object on success.
    """
    # Deferred import breaks the circular dependency:
    # roles.py → dependencies.py → crud_user → models → roles.py
    from app.dependencies import get_current_active_user

    def checker(current_user: User = Depends(get_current_active_user)) -> User:
        """Inner dependency injected by FastAPI's DI system."""
        if current_user.role not in [r.value for r in roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {[r.value for r in roles]}",
            )
        return current_user

    return checker
