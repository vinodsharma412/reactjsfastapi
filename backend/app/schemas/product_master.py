from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, field_validator


class ProductIn(BaseModel):
    title:        str
    product_desc: Optional[str] = None
    bullet_1: Optional[str] = None
    bullet_2: Optional[str] = None
    bullet_3: Optional[str] = None
    bullet_4: Optional[str] = None
    bullet_5: Optional[str] = None
    bullet_6: Optional[str] = None
    image_1: Optional[str] = None
    image_2: Optional[str] = None
    image_3: Optional[str] = None
    image_4: Optional[str] = None
    image_5: Optional[str] = None
    image_6: Optional[str] = None
    keywords: Optional[List[str]] = []

    @field_validator('keywords', mode='before')
    @classmethod
    def coerce_keywords(cls, v):
        return v if isinstance(v, list) else []


class ProductOut(ProductIn):
    id:         int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class WordSuggestionIn(BaseModel):
    phrase:    str
    word_type: str  # not_use | can_use | brand


class WordSuggestionOut(WordSuggestionIn):
    id:         int
    created_at: Optional[datetime]

    class Config:
        from_attributes = True
