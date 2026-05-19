from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    username        = Column(String(100), unique=True, nullable=False, index=True)
    email           = Column(String(150), unique=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    full_name       = Column(String(200), nullable=True)
    is_active       = Column(Boolean, default=True)
    is_admin        = Column(Boolean, default=False)
    role            = Column(String(50), nullable=False, default="viewer")
    avatar_url      = Column(String(255), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())
