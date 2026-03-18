"""
Stock Portfolio Tracker API
Author: Divyansh Kharnal
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
import os

from app.database import engine, get_db, Base
from app import models, schemas, stock_service

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Stock Portfolio Tracker",
    description="REST API for managing stock portfolios with real-time market data and financial analytics.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Static frontend ──────────────────────────────────────────────────────────
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    index = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"status": "ok", "message": "Stock Portfolio Tracker API is running."}

@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "message": "Stock Portfolio Tracker API is running."}


# ── Portfolio CRUD ────────────────────────────────────────────────────────────

@app.post("/portfolio", response_model=schemas.HoldingOut, tags=["Portfolio"])
def add_holding(holding: schemas.HoldingCreate, db: Session = Depends(get_db)):
    """Add a stock holding to your portfolio."""
    price = stock_service.get_current_price(holding.ticker.upper())
    if price is None:
        raise HTTPException(status_code=404, detail=f"Ticker '{holding.ticker}' not found.")

    existing = db.query(models.Holding).filter(
        models.Holding.ticker == holding.ticker.upper()
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"'{holding.ticker}' already in portfolio. Use PUT to update.")

    db_holding = models.Holding(
        ticker=holding.ticker.upper(),
        shares=holding.shares,
        avg_buy_price=holding.avg_buy_price
    )
    db.add(db_holding)
    db.commit()
    db.refresh(db_holding)
    return db_holding


@app.get("/portfolio", response_model=List[schemas.HoldingOut], tags=["Portfolio"])
def get_portfolio(db: Session = Depends(get_db)):
    """List all holdings."""
    return db.query(models.Holding).all()


@app.put("/portfolio/{ticker}", response_model=schemas.HoldingOut, tags=["Portfolio"])
def update_holding(ticker: str, update: schemas.HoldingCreate, db: Session = Depends(get_db)):
    """Update shares or average buy price for an existing holding."""
    holding = db.query(models.Holding).filter(
        models.Holding.ticker == ticker.upper()
    ).first()
    if not holding:
        raise HTTPException(status_code=404, detail=f"'{ticker}' not in portfolio.")
    holding.shares = update.shares
    holding.avg_buy_price = update.avg_buy_price
    db.commit()
    db.refresh(holding)
    return holding


@app.delete("/portfolio/{ticker}", tags=["Portfolio"])
def remove_holding(ticker: str, db: Session = Depends(get_db)):
    """Remove a holding by ticker."""
    holding = db.query(models.Holding).filter(
        models.Holding.ticker == ticker.upper()
    ).first()
    if not holding:
        raise HTTPException(status_code=404, detail=f"'{ticker}' not in portfolio.")
    db.delete(holding)
    db.commit()
    return {"message": f"{ticker.upper()} removed from portfolio."}


# ── Portfolio Analytics ───────────────────────────────────────────────────────

@app.get("/portfolio/summary", response_model=schemas.PortfolioSummary, tags=["Portfolio"])
def get_portfolio_summary(db: Session = Depends(get_db)):
    """Full P&L breakdown with live prices for every holding."""
    holdings = db.query(models.Holding).all()
    if not holdings:
        raise HTTPException(status_code=404, detail="Portfolio is empty.")
    summary = stock_service.build_portfolio_summary(holdings)
    if summary is None:
        raise HTTPException(status_code=503, detail="Could not fetch live prices. Try again shortly.")
    return summary


# ── Market Data ───────────────────────────────────────────────────────────────

@app.get("/quote/{ticker}", response_model=schemas.StockQuote, tags=["Market Data"])
def get_quote(ticker: str):
    """Real-time quote: price, change %, volume, market cap."""
    quote = stock_service.get_full_quote(ticker.upper())
    if quote is None:
        raise HTTPException(status_code=404, detail=f"Could not fetch data for '{ticker}'.")
    return quote


@app.get("/history/{ticker}", response_model=List[schemas.PricePoint], tags=["Market Data"])
def get_history(ticker: str, days: int = 30):
    """Historical daily closing prices (1–365 days)."""
    if not 1 <= days <= 365:
        raise HTTPException(status_code=400, detail="days must be between 1 and 365.")
    history = stock_service.get_price_history(ticker.upper(), days)
    if not history:
        raise HTTPException(status_code=404, detail=f"No history found for '{ticker}'.")
    return history


@app.get("/metrics/{ticker}", response_model=schemas.StockMetrics, tags=["Market Data"])
def get_metrics(ticker: str):
    """Technical indicators: MA-20, MA-50, RSI-14, annualised volatility, trend signal."""
    metrics = stock_service.compute_metrics(ticker.upper())
    if metrics is None:
        raise HTTPException(status_code=404, detail=f"Could not compute metrics for '{ticker}'.")
    return metrics

@app.get("/debug/history/{ticker}")
async def debug_history(ticker: str):
    import requests
    from datetime import datetime, timedelta
    end = int(datetime.utcnow().timestamp())
    start = int((datetime.utcnow() - timedelta(days=40)).timestamp())
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
        params={"period1": start, "period2": end, "interval": "1d"},
        headers=headers, timeout=15)
    return {"status": r.status_code, "body": r.text[:500]}
