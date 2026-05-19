from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class Menu(Base):
    __tablename__ = "menus"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(100), nullable=False)
    path       = Column(String(200), nullable=False, unique=True)
    icon       = Column(String(100), nullable=True)
    parent_id  = Column(Integer, ForeignKey('menus.id'), nullable=True)
    sort_order = Column(Integer, default=0)
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    accesses = relationship("MenuAccess", back_populates="menu", cascade="all, delete-orphan")


class MenuAccess(Base):
    __tablename__ = "menu_access"

    id         = Column(Integer, primary_key=True, index=True)
    menu_id    = Column(Integer, ForeignKey('menus.id', ondelete='CASCADE'), nullable=False)
    role       = Column(String(50), nullable=False)
    can_view   = Column(Boolean, default=False)
    can_insert = Column(Boolean, default=False)
    can_update = Column(Boolean, default=False)
    can_delete = Column(Boolean, default=False)

    menu = relationship("Menu", back_populates="accesses")
