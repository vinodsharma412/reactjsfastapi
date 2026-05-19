"""Stock data, portfolio, watchlist, and screener endpoints.

All routes require an authenticated active user (``get_current_active_user``).
Service calls are delegated to ``stock_service`` and ``sentiment_service``; the
endpoints themselves contain only HTTP-layer logic (validation, 502 promotion).

Route summary:
    GET  /search                         — ticker/company search
    GET  /basic/{symbol}                 — fast quote (fast_info, ~1 s)
    GET  /market/global                  — global indices snapshot
    GET  /analyse/{symbol}               — full analysis + composite recommendation
    GET  /chart/{symbol}                 — OHLCV candlestick history
    GET  /sentiment/{symbol}             — news sentiment
    GET  /screener                       — dividend + P/E + score screener
    GET  /financials/{symbol}            — full financial statements
    GET  /portfolio                      — holdings + P&L summary
    GET  /portfolio/insights             — per-holding action recommendations
    POST /portfolio/transactions         — record a buy/sell/dividend
    DELETE /portfolio/transactions/{id}  — remove a transaction
    GET  /watchlist                      — list watchlist items
    POST /watchlist                      — add a symbol to watchlist
    DELETE /watchlist/{id}               — remove from watchlist
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_active_user
from app.models.stock import StockTransaction, StockWatchlist
from app.models.user import User
from app.schemas.stock import (
    PortfolioSummary,
    TransactionIn,
    TransactionOut,
    WatchlistIn,
    WatchlistOut,
)
from app.services import sentiment_service, stock_service

router = APIRouter()


# ── Search ─────────────────────────────────────────────────────────────────────


@router.get("/search")
def search(
    q: str = Query(..., min_length=1),
    _: User = Depends(get_current_active_user),
) -> list:
    """Search the NSE equity universe by symbol or company name.

    Args:
        q: Search string (minimum 1 character).
        _: Auth guard.

    Returns:
        Up to 20 dicts with ``symbol`` and ``company_name``.
    """
    return stock_service.search_stocks(q)


# ── Fast basic quote ───────────────────────────────────────────────────────────


@router.get("/basic/{symbol}")
def basic_quote(
    symbol: str,
    _: User = Depends(get_current_active_user),
) -> dict:
    """Return a fast price quote using ``yf.Ticker.fast_info`` (~1 s response).

    Args:
        symbol: NSE ticker symbol (case-insensitive).
        _: Auth guard.

    Returns:
        Quote dict with ``current_price``, ``change_pct``, SMA, year range, etc.

    Raises:
        HTTPException 502: If yfinance fails for the symbol.
    """
    data = stock_service.get_basic_quote(symbol.upper())
    if data.get("error"):
        raise HTTPException(status_code=502, detail=data["error"])
    return data


# ── Global market indices ──────────────────────────────────────────────────────


@router.get("/market/global")
def global_markets(_: User = Depends(get_current_active_user)) -> list:
    """Return a snapshot of global market indices (Nifty, S&P 500, Nikkei, etc.).

    Args:
        _: Auth guard.

    Returns:
        List of index dicts with ``name``, ``price``, ``change_pct``, etc.
    """
    return stock_service.get_global_markets()


# ── Stock analysis ─────────────────────────────────────────────────────────────


@router.get("/analyse/{symbol}")
def analyse(
    symbol: str,
    _: User = Depends(get_current_active_user),
) -> dict:
    """Run full technical + fundamental analysis for *symbol*.

    Fetches sentiment first and merges the score into the composite
    recommendation before returning.

    Args:
        symbol: NSE ticker symbol (case-insensitive).
        _: Auth guard.

    Returns:
        Analysis dict including ``technicals``, ``recommendation``,
        ``valuation``, ``entry_exit``, and ``sector_schemes``.

    Raises:
        HTTPException 502: If the yfinance data fetch fails.
    """
    sym = symbol.upper()
    sent = sentiment_service.analyze_sentiment(sym)
    data = stock_service.get_stock_analysis(sym, sent.get("score", 0.0))
    if data.get("error"):
        raise HTTPException(status_code=502, detail=data["error"])
    return data


@router.get("/chart/{symbol}")
def chart(
    symbol: str,
    period: str = Query("1y"),
    _: User = Depends(get_current_active_user),
) -> list:
    """Return OHLCV candlestick data for the requested period.

    Args:
        symbol: NSE ticker symbol (case-insensitive).
        period: History period (``"1d"``, ``"1y"``, ``"2y"``, etc.).
        _: Auth guard.

    Returns:
        List of OHLCV dicts with ``date``, ``open``, ``high``, ``low``,
        ``close``, ``volume``.

    Raises:
        HTTPException 404: If no data is available for the symbol/period.
    """
    rows = stock_service.get_chart_data(symbol.upper(), period)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No chart data available for this symbol.",
        )
    return rows


@router.get("/sentiment/{symbol}")
def sentiment(
    symbol: str,
    _: User = Depends(get_current_active_user),
) -> dict:
    """Return news sentiment analysis for *symbol*.

    Args:
        symbol: NSE ticker symbol (case-insensitive).
        _: Auth guard.

    Returns:
        Sentiment dict with ``score``, ``label``, ``confidence``,
        ``headlines``, ``intl_news``, and ``macro_news``.
    """
    name = stock_service.NSE_UNIVERSE.get(symbol.upper(), "")
    return sentiment_service.analyze_sentiment(symbol.upper(), name)


# ── Screener ───────────────────────────────────────────────────────────────────


@router.get("/screener")
def screener(
    min_yield: float = Query(0.03, ge=0.0, le=0.20),
    max_pe: float = Query(50.0, ge=0.0),
    min_score: int = Query(0),
    _: User = Depends(get_current_active_user),
) -> list:
    """Screen NSE stocks by dividend yield, P/E ratio, and composite score.

    Args:
        min_yield: Minimum dividend yield (0 = no filter).
        max_pe: Maximum trailing P/E ratio.
        min_score: Minimum composite recommendation score (0 = no filter).
        _: Auth guard.

    Returns:
        Filtered and sorted list of up to 40 stock summary dicts.
    """
    results = stock_service.screen_stocks(min_yield, max_pe, min_score)
    if min_score:
        results = [r for r in results if (r.get("score") or 0) >= min_score]
    return results


# ── Detailed financial statements ──────────────────────────────────────────────


@router.get("/financials/{symbol}")
def financials(
    symbol: str,
    _: User = Depends(get_current_active_user),
) -> dict:
    """Return full financial statements (P&L, Balance Sheet, Cash Flow, Ratios).

    Args:
        symbol: NSE ticker symbol (case-insensitive).
        _: Auth guard.

    Returns:
        Financial data dict with annual and quarterly breakdowns.

    Raises:
        HTTPException 502: If the yfinance data fetch fails.
    """
    data = stock_service.get_detailed_financials(symbol.upper())
    if data.get("error"):
        raise HTTPException(status_code=502, detail=data["error"])
    return data


# ── Portfolio / Transactions ───────────────────────────────────────────────────


@router.get("/portfolio", response_model=PortfolioSummary)
def get_portfolio(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> PortfolioSummary:
    """Return the user's portfolio holdings, P&L, and transaction history.

    Args:
        db: Database session.
        _: Auth guard.

    Returns:
        ``PortfolioSummary`` with ``total_invested``, ``current_value``,
        ``total_pnl``, ``pnl_pct``, ``holdings``, and ``transactions``.
    """
    txns = db.query(StockTransaction).order_by(StockTransaction.created_at.desc()).all()
    pnl = stock_service.calculate_portfolio(txns)
    return PortfolioSummary(
        total_invested=pnl["total_invested"],
        current_value=pnl["current_value"],
        total_pnl=pnl["total_pnl"],
        pnl_pct=pnl["pnl_pct"],
        holdings=pnl["holdings"],
        transactions=[TransactionOut.model_validate(t) for t in txns],
    )


@router.get("/portfolio/insights")
def portfolio_insights(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> list:
    """Return actionable recommendations for each portfolio holding.

    Uses cached technical analysis — no additional yfinance calls.

    Args:
        db: Database session.
        _: Auth guard.

    Returns:
        List of insight dicts sorted by urgency (``"high"`` first).
    """
    txns = db.query(StockTransaction).order_by(StockTransaction.created_at.asc()).all()
    pnl = stock_service.calculate_portfolio(txns)
    return stock_service.generate_portfolio_insights(pnl["holdings"])


@router.post("/portfolio/transactions", response_model=TransactionOut)
def add_transaction(
    payload: TransactionIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> StockTransaction:
    """Record a new stock transaction (buy, sell, or dividend).

    ``total_amount`` is computed as ``quantity × price ± brokerage``.
    Sell transactions are stored with a negative sign on quantity/amount so
    ``calculate_portfolio`` can reverse the cost basis correctly.

    Args:
        payload: Validated ``TransactionIn`` schema.
        db: Database session.
        _: Auth guard.

    Returns:
        The newly created ``StockTransaction`` ORM object.
    """
    sign = -1 if payload.transaction_type == "sell" else 1
    total_amount = sign * payload.quantity * payload.price + payload.brokerage
    record = StockTransaction(
        symbol=payload.symbol.upper(),
        company_name=(
            payload.company_name
            or stock_service.NSE_UNIVERSE.get(payload.symbol.upper(), "")
        ),
        transaction_type=payload.transaction_type,
        quantity=payload.quantity,
        price=payload.price,
        total_amount=abs(total_amount),
        brokerage=payload.brokerage,
        notes=payload.notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/portfolio/transactions/{txn_id}", status_code=204)
def delete_transaction(
    txn_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> None:
    """Permanently delete a transaction record.

    Args:
        txn_id: Primary key of the ``StockTransaction`` to delete.
        db: Database session.
        _: Auth guard.

    Raises:
        HTTPException 404: If no transaction exists with *txn_id*.
    """
    txn = db.query(StockTransaction).filter(StockTransaction.id == txn_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    db.delete(txn)
    db.commit()


# ── Watchlist ──────────────────────────────────────────────────────────────────


@router.get("/watchlist", response_model=List[WatchlistOut])
def list_watchlist(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> list:
    """Return all watchlist entries for the current user.

    Args:
        db: Database session.
        _: Auth guard.

    Returns:
        List of ``StockWatchlist`` objects ordered newest first.
    """
    return db.query(StockWatchlist).order_by(StockWatchlist.added_at.desc()).all()


@router.post("/watchlist", response_model=WatchlistOut)
def add_watchlist(
    payload: WatchlistIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> StockWatchlist:
    """Add a symbol to the watchlist.

    Args:
        payload: ``WatchlistIn`` with symbol, optional target price and stop loss.
        db: Database session.
        _: Auth guard.

    Returns:
        The newly created ``StockWatchlist`` ORM object.

    Raises:
        HTTPException 409: If the symbol is already in the watchlist.
    """
    sym = payload.symbol.upper()
    existing = db.query(StockWatchlist).filter(StockWatchlist.symbol == sym).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"{sym} is already in your watchlist.")
    record = StockWatchlist(
        symbol=sym,
        company_name=(
            payload.company_name or stock_service.NSE_UNIVERSE.get(sym, "")
        ),
        target_price=payload.target_price,
        stop_loss=payload.stop_loss,
        notes=payload.notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/watchlist/{wl_id}", status_code=204)
def remove_watchlist(
    wl_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> None:
    """Remove an item from the watchlist.

    Args:
        wl_id: Primary key of the ``StockWatchlist`` row to delete.
        db: Database session.
        _: Auth guard.

    Raises:
        HTTPException 404: If no watchlist item exists with *wl_id*.
    """
    item = db.query(StockWatchlist).filter(StockWatchlist.id == wl_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist item not found.")
    db.delete(item)
    db.commit()
