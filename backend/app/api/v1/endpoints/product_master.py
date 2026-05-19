from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_active_user
from app.models.user import User
from app.models.product_master import ProductMaster, WordSuggestion
from app.schemas.product_master import (
    ProductIn, ProductOut,
    WordSuggestionIn, WordSuggestionOut,
)

product_router    = APIRouter()
suggestion_router = APIRouter()

_VALID_TYPES = {'not_use', 'can_use', 'brand'}


# ── Products ──────────────────────────────────────────────────────────────────

@product_router.get("/", response_model=List[ProductOut])
def list_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return db.query(ProductMaster).order_by(ProductMaster.created_at.desc()).all()


@product_router.post("/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    product = ProductMaster(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@product_router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    product = db.query(ProductMaster).filter(ProductMaster.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    return product


@product_router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    payload: ProductIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    product = db.query(ProductMaster).filter(ProductMaster.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    for key, val in payload.model_dump().items():
        setattr(product, key, val)
    product.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(product)
    return product


@product_router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    product = db.query(ProductMaster).filter(ProductMaster.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    db.delete(product)
    db.commit()


# ── Word Suggestions ──────────────────────────────────────────────────────────

@suggestion_router.get("/", response_model=List[WordSuggestionOut])
def list_suggestions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return (
        db.query(WordSuggestion)
        .order_by(WordSuggestion.word_type, WordSuggestion.phrase)
        .all()
    )


@suggestion_router.post("/", response_model=WordSuggestionOut, status_code=status.HTTP_201_CREATED)
def create_suggestion(
    payload: WordSuggestionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if payload.word_type not in _VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail="word_type must be one of: not_use, can_use, brand",
        )
    phrase = payload.phrase.strip()
    if not phrase:
        raise HTTPException(status_code=400, detail="phrase cannot be empty.")
    suggestion = WordSuggestion(phrase=phrase, word_type=payload.word_type)
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    return suggestion


@suggestion_router.delete("/{suggestion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_suggestion(
    suggestion_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    suggestion = db.query(WordSuggestion).filter(WordSuggestion.id == suggestion_id).first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found.")
    db.delete(suggestion)
    db.commit()
