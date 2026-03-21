"""
StockPulse API
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
    title="StockPulse",
    description="REST API for managing stock portfolios with real-time market data and financial analytics.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", tags=["Health"])
def root():
    index = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"status": "ok", "version": "1.0.0"}

@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "message": "StockPulse API is running."}


@app.post("/portfolio", response_model=schemas.HoldingOut, tags=["Portfolio"])
def add_holding(holding: schemas.HoldingCreate, db: Session = Depends(get_db)):
    price = stock_service.get_current_price(holding.ticker.upper())
    if price is None:
        raise HTTPException(status_code=404, detail=f"Ticker '{holding.ticker}' not found.")
    existing = db.query(models.Holding).filter(models.Holding.ticker == holding.ticker.upper()).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"'{holding.ticker}' already in portfolio. Use PUT to update.")
    db_holding = models.Holding(ticker=holding.ticker.upper(), shares=holding.shares, avg_buy_price=holding.avg_buy_price)
    db.add(db_holding)
    db.commit()
    db.refresh(db_holding)
    return db_holding

@app.get("/portfolio", response_model=List[schemas.HoldingOut], tags=["Portfolio"])
def get_portfolio(db: Session = Depends(get_db)):
    return db.query(models.Holding).all()

@app.put("/portfolio/{ticker}", response_model=schemas.HoldingOut, tags=["Portfolio"])
def update_holding(ticker: str, update: schemas.HoldingCreate, db: Session = Depends(get_db)):
    holding = db.query(models.Holding).filter(models.Holding.ticker == ticker.upper()).first()
    if not holding:
        raise HTTPException(status_code=404, detail=f"'{ticker}' not in portfolio.")
    holding.shares = update.shares
    holding.avg_buy_price = update.avg_buy_price
    db.commit()
    db.refresh(holding)
    return holding

@app.delete("/portfolio/{ticker}", tags=["Portfolio"])
def remove_holding(ticker: str, db: Session = Depends(get_db)):
    holding = db.query(models.Holding).filter(models.Holding.ticker == ticker.upper()).first()
    if not holding:
        raise HTTPException(status_code=404, detail=f"'{ticker}' not in portfolio.")
    db.delete(holding)
    db.commit()
    return {"message": f"{ticker.upper()} removed from portfolio."}

@app.get("/portfolio/summary", response_model=schemas.PortfolioSummary, tags=["Portfolio"])
def get_portfolio_summary(db: Session = Depends(get_db)):
    holdings = db.query(models.Holding).all()
    if not holdings:
        raise HTTPException(status_code=404, detail="Portfolio is empty.")
    summary = stock_service.build_portfolio_summary(holdings)
    if summary is None:
        raise HTTPException(status_code=503, detail="Could not fetch live prices.")
    return summary

@app.get("/quote/{ticker}", response_model=schemas.StockQuote, tags=["Market Data"])
def get_quote(ticker: str):
    quote = stock_service.get_full_quote(ticker.upper())
    if quote is None:
        raise HTTPException(status_code=404, detail=f"Could not fetch data for '{ticker}'.")
    return quote

@app.get("/history/{ticker}", response_model=List[schemas.PricePoint], tags=["Market Data"])
def get_history(ticker: str, days: int = 30):
    if not 1 <= days <= 365:
        raise HTTPException(status_code=400, detail="days must be between 1 and 365.")
    history = stock_service.get_price_history(ticker.upper(), days)
    if not history:
        raise HTTPException(status_code=404, detail=f"No history found for '{ticker}'.")
    return history

@app.get("/metrics/{ticker}", response_model=schemas.StockMetrics, tags=["Market Data"])
def get_metrics(ticker: str):
    metrics = stock_service.compute_metrics(ticker.upper())
    if metrics is None:
        raise HTTPException(status_code=404, detail=f"Could not compute metrics for '{ticker}'.")
    return metrics

@app.get("/debug/finnhub/{ticker}")
async def debug_finnhub(ticker: str):
    import requests
    from datetime import datetime, timedelta
    end   = int(datetime.utcnow().timestamp())
    start = int((datetime.utcnow() - timedelta(days=40)).timestamp())
    key   = os.getenv("FINNHUB_API_KEY", "")
    r = requests.get("https://finnhub.io/api/v1/stock/candle",
        params={"symbol": ticker, "resolution": "D", "from": start, "to": end, "token": key},
        timeout=15)
    return {"status": r.status_code, "body": r.json()}

@app.get("/news/{ticker}", tags=["Market Data"])
def get_news(ticker: str):
    return stock_service.get_company_news(ticker.upper())

@app.get("/market/overview", tags=["Market Data"])
def market_overview():
    return stock_service.get_market_overview()

@app.get("/candles/{ticker}", tags=["Market Data"])
def get_candles(ticker: str, days: int = 30):
    if not 1 <= days <= 365:
        raise HTTPException(status_code=400, detail="days must be between 1 and 365.")
    data = stock_service.get_candles(ticker.upper(), days)
    if not data:
        raise HTTPException(status_code=404, detail=f"No candle data for '{ticker}'.")
    return data

@app.get("/portfolio/chart", tags=["Portfolio"])
def portfolio_chart(db: Session = Depends(get_db)):
    holdings = db.query(models.Holding).all()
    if not holdings:
        raise HTTPException(status_code=404, detail="Portfolio is empty.")
    return stock_service.get_portfolio_chart(holdings)
@app.get("/debug/av/{ticker}")
async def debug_av(ticker: str):
    import requests, os
    key = os.getenv("ALPHA_VANTAGE_KEY", "NOT_SET")
    r = requests.get("https://www.alphavantage.co/query", params={
        "function": "TIME_SERIES_DAILY",
        "symbol": ticker,
        "outputsize": "compact",
        "apikey": key
    }, timeout=15)
    return {"status": r.status_code, "key_set": key != "NOT_SET", "body": r.json()}
