from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from app.db.base import Base


class ProductMaster(Base):
    __tablename__ = "product_master"

    id           = Column(Integer, primary_key=True, index=True)
    title        = Column(String(500), nullable=False)
    product_desc = Column(Text, nullable=True)

    bullet_1 = Column(Text, nullable=True)
    bullet_2 = Column(Text, nullable=True)
    bullet_3 = Column(Text, nullable=True)
    bullet_4 = Column(Text, nullable=True)
    bullet_5 = Column(Text, nullable=True)
    bullet_6 = Column(Text, nullable=True)

    image_1 = Column(String(1000), nullable=True)
    image_2 = Column(String(1000), nullable=True)
    image_3 = Column(String(1000), nullable=True)
    image_4 = Column(String(1000), nullable=True)
    image_5 = Column(String(1000), nullable=True)
    image_6 = Column(String(1000), nullable=True)

    keywords = Column(JSON, nullable=True, default=list)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WordSuggestion(Base):
    __tablename__ = "word_suggestions"

    id         = Column(Integer, primary_key=True, index=True)
    phrase     = Column(String(500), nullable=False)
    word_type  = Column(String(20), nullable=False)  # not_use | can_use | brand
    created_at = Column(DateTime, default=datetime.utcnow)
