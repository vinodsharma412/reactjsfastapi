from typing import List, Optional
from sqlalchemy.orm import Session
from app.crud.base import CRUDBase
from app.models.menu import Menu, MenuAccess
from app.schemas.menu import MenuCreate, MenuUpdate, MenuAccessCreate, MenuAccessUpdate


class CRUDMenu(CRUDBase[Menu]):
    def get_all_active(self, db: Session) -> List[Menu]:
        return db.query(Menu).filter(Menu.is_active == True).order_by(Menu.sort_order).all()

    def create_menu(self, db: Session, menu_in: MenuCreate) -> Menu:
        menu = Menu(**menu_in.dict())
        db.add(menu)
        db.commit()
        db.refresh(menu)
        return menu

    def update_menu(self, db: Session, id: int, menu_in: MenuUpdate) -> Optional[Menu]:
        menu = self.get(db, id)
        if not menu:
            return None
        for field, value in menu_in.dict(exclude_unset=True).items():
            setattr(menu, field, value)
        db.commit()
        db.refresh(menu)
        return menu

    def get_menus_for_role(self, db: Session, role: str) -> List[dict]:
        results = (
            db.query(Menu, MenuAccess)
            .join(MenuAccess, Menu.id == MenuAccess.menu_id)
            .filter(
                MenuAccess.role == role,
                MenuAccess.can_view == True,
                Menu.is_active == True,
            )
            .order_by(Menu.sort_order)
            .all()
        )
        return [
            {
                "id": menu.id,
                "name": menu.name,
                "path": menu.path,
                "icon": menu.icon,
                "sort_order": menu.sort_order,
                "can_view":   access.can_view,
                "can_insert": access.can_insert,
                "can_update": access.can_update,
                "can_delete": access.can_delete,
            }
            for menu, access in results
        ]


class CRUDMenuAccess(CRUDBase[MenuAccess]):
    def get_all_with_menu(self, db: Session) -> List[dict]:
        results = (
            db.query(MenuAccess, Menu.name.label("menu_name"))
            .join(Menu, MenuAccess.menu_id == Menu.id)
            .order_by(Menu.sort_order, MenuAccess.role)
            .all()
        )
        return [
            {
                "id":         access.id,
                "menu_id":    access.menu_id,
                "menu_name":  menu_name,
                "role":       access.role,
                "can_view":   access.can_view,
                "can_insert": access.can_insert,
                "can_update": access.can_update,
                "can_delete": access.can_delete,
            }
            for access, menu_name in results
        ]

    def get_by_menu_and_role(self, db: Session, menu_id: int, role: str) -> Optional[MenuAccess]:
        return db.query(MenuAccess).filter(
            MenuAccess.menu_id == menu_id,
            MenuAccess.role == role,
        ).first()

    def upsert(self, db: Session, access_in: MenuAccessCreate) -> MenuAccess:
        existing = self.get_by_menu_and_role(db, access_in.menu_id, access_in.role)
        if existing:
            for field, value in access_in.dict().items():
                setattr(existing, field, value)
            db.commit()
            db.refresh(existing)
            return existing
        access = MenuAccess(**access_in.dict())
        db.add(access)
        db.commit()
        db.refresh(access)
        return access

    def update_access(self, db: Session, id: int, access_in: MenuAccessUpdate) -> Optional[MenuAccess]:
        access = self.get(db, id)
        if not access:
            return None
        for field, value in access_in.dict(exclude_unset=True).items():
            setattr(access, field, value)
        db.commit()
        db.refresh(access)
        return access


crud_menu = CRUDMenu(Menu)
crud_menu_access = CRUDMenuAccess(MenuAccess)
