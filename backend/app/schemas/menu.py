from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class MenuBase(BaseModel):
    name: str
    path: str
    icon: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: int = 0
    is_active: bool = True


class MenuCreate(MenuBase):
    pass


class MenuUpdate(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    icon: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class MenuResponse(MenuBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class MenuWithAccess(BaseModel):
    id: int
    name: str
    path: str
    icon: Optional[str] = None
    sort_order: int
    can_view: bool
    can_insert: bool
    can_update: bool
    can_delete: bool

    class Config:
        from_attributes = True


class MenuAccessBase(BaseModel):
    menu_id: int
    role: str
    can_view: bool = False
    can_insert: bool = False
    can_update: bool = False
    can_delete: bool = False


class MenuAccessCreate(MenuAccessBase):
    pass


class MenuAccessUpdate(BaseModel):
    can_view: Optional[bool] = None
    can_insert: Optional[bool] = None
    can_update: Optional[bool] = None
    can_delete: Optional[bool] = None


class MenuAccessResponse(MenuAccessBase):
    id: int
    menu_name: Optional[str] = None

    class Config:
        from_attributes = True
