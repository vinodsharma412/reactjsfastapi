from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base


class StockTransaction(Base):
    __tablename__ = "stock_transactions"

    id               = Column(Integer, primary_key=True, index=True)
    symbol           = Column(String(30), nullable=False, index=True)
    company_name     = Column(String(200))
    transaction_type = Column(String(10), nullable=False)   # buy | sell | dividend
    quantity         = Column(Float, nullable=False)
    price            = Column(Float, nullable=False)
    total_amount     = Column(Float, nullable=False)
    brokerage        = Column(Float, default=0.0)
    notes            = Column(Text, nullable=True)
    created_at       = Column(DateTime(timezone=False), server_default=func.now())


class StockWatchlist(Base):
    __tablename__ = "stock_watchlist"

    id           = Column(Integer, primary_key=True, index=True)
    symbol       = Column(String(30), unique=True, nullable=False, index=True)
    company_name = Column(String(200))
    target_price = Column(Float, nullable=True)
    stop_loss    = Column(Float, nullable=True)
    notes        = Column(Text, nullable=True)
    added_at     = Column(DateTime(timezone=False), server_default=func.now())
