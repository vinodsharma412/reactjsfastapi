from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, field_validator
import re


class JobCreate(BaseModel):
    asins: List[str]

    @field_validator("asins")
    @classmethod
    def validate_asins(cls, v):
        cleaned = []
        for raw in v:
            asin = raw.strip().upper()
            if asin and re.match(r"^[A-Z0-9]{10}$", asin):
                cleaned.append(asin)
        if not cleaned:
            raise ValueError("No valid ASINs provided (each must be 10 alphanumeric characters).")
        if len(cleaned) > 50:
            raise ValueError("Maximum 50 ASINs per request.")
        return cleaned


class ProductDataOut(BaseModel):
    asin: str
    title: Optional[str] = None
    brand: Optional[str] = None
    price: Optional[str] = None
    rating: Optional[str] = None
    review_count: Optional[str] = None
    availability: Optional[str] = None
    image_url: Optional[str] = None
    scraped_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TaskOut(BaseModel):
    id: int
    asin: str
    status: str
    error: Optional[str] = None
    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    product: Optional[ProductDataOut] = None

    class Config:
        from_attributes = True


class JobOut(BaseModel):
    id: int
    user_id: int
    username: Optional[str] = None
    total: int
    pending: int
    running: int
    completed: int
    failed: int
    created_at: datetime
    tasks: Optional[List[TaskOut]] = None

    class Config:
        from_attributes = True
