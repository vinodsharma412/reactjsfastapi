from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.roles import Role, require_roles
from app.crud.menu import crud_menu, crud_menu_access
from app.db.session import get_db
from app.dependencies import get_current_active_user
from app.models.user import User
from app.models.menu import Menu as MenuModel
from app.schemas.menu import (
    MenuCreate, MenuResponse, MenuUpdate, MenuWithAccess,
    MenuAccessCreate, MenuAccessResponse, MenuAccessUpdate,
)

router = APIRouter()


# ── My menus (for the sidebar) ──────────────────────────────────────────────

@router.get("/my-menus", response_model=List[MenuWithAccess])
def get_my_menus(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return crud_menu.get_menus_for_role(db, current_user.role)


# ── Menu CRUD (admin only) ───────────────────────────────────────────────────

@router.get("/", response_model=List[MenuResponse])
def list_menus(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
):
    return db.query(MenuModel).order_by(MenuModel.sort_order).all()


@router.post("/", response_model=MenuResponse, status_code=status.HTTP_201_CREATED)
def create_menu(
    menu_in: MenuCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
):
    return crud_menu.create_menu(db, menu_in)


@router.put("/{menu_id}", response_model=MenuResponse)
def update_menu(
    menu_id: int,
    menu_in: MenuUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
):
    menu = crud_menu.update_menu(db, menu_id, menu_in)
    if not menu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")
    return menu


@router.delete("/{menu_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_menu(
    menu_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
):
    menu = crud_menu.get(db, menu_id)
    if not menu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")
    crud_menu.delete(db, menu_id)


# ── Menu Access CRUD (admin only) ────────────────────────────────────────────

@router.get("/access/", response_model=List[MenuAccessResponse])
def list_menu_access(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
):
    return crud_menu_access.get_all_with_menu(db)


@router.post("/access/", response_model=MenuAccessResponse, status_code=status.HTTP_201_CREATED)
def upsert_menu_access(
    access_in: MenuAccessCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
):
    return crud_menu_access.upsert(db, access_in)


@router.put("/access/{access_id}", response_model=MenuAccessResponse)
def update_menu_access(
    access_id: int,
    access_in: MenuAccessUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
):
    access = crud_menu_access.update_access(db, access_id, access_in)
    if not access:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access record not found")
    return access


@router.delete("/access/{access_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_menu_access(
    access_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
):
    access = crud_menu_access.get(db, access_id)
    if not access:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access record not found")
    crud_menu_access.delete(db, access_id)
