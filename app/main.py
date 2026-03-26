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

from dotenv import load_dotenv
load_dotenv()

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


# ── HEALTH ────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    index = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"status": "ok", "version": "1.0.0"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "message": "StockPulse API is running."}


# ── PORTFOLIO CRUD ────────────────────────────────────────────────────────────

@app.post("/portfolio", response_model=schemas.HoldingOut, tags=["Portfolio"])
async def add_holding(holding: schemas.HoldingCreate, db: Session = Depends(get_db)):
    price = stock_service.get_current_price(holding.ticker.upper())
    if price is None:
        raise HTTPException(status_code=404, detail=f"Ticker '{holding.ticker}' not found.")
    existing = db.query(models.Holding).filter(models.Holding.ticker == holding.ticker.upper()).first()
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
async def get_portfolio(db: Session = Depends(get_db)):
    return db.query(models.Holding).all()


@app.put("/portfolio/{ticker}", response_model=schemas.HoldingOut, tags=["Portfolio"])
async def update_holding(ticker: str, update: schemas.HoldingCreate, db: Session = Depends(get_db)):
    holding = db.query(models.Holding).filter(models.Holding.ticker == ticker.upper()).first()
    if not holding:
        raise HTTPException(status_code=404, detail=f"'{ticker}' not in portfolio.")
    holding.shares = update.shares
    holding.avg_buy_price = update.avg_buy_price
    db.commit()
    db.refresh(holding)
    return holding


@app.delete("/portfolio/{ticker}", tags=["Portfolio"])
async def remove_holding(ticker: str, db: Session = Depends(get_db)):
    holding = db.query(models.Holding).filter(models.Holding.ticker == ticker.upper()).first()
    if not holding:
        raise HTTPException(status_code=404, detail=f"'{ticker}' not in portfolio.")
    db.delete(holding)
    db.commit()
    return {"message": f"{ticker.upper()} removed from portfolio."}


@app.get("/portfolio/summary", response_model=schemas.PortfolioSummary, tags=["Portfolio"])
async def get_portfolio_summary(db: Session = Depends(get_db)):
    holdings = db.query(models.Holding).all()
    if not holdings:
        raise HTTPException(status_code=404, detail="Portfolio is empty.")
    summary = stock_service.build_portfolio_summary(holdings)
    if summary is None:
        raise HTTPException(status_code=503, detail="Could not fetch live prices.")
    return summary


@app.get("/portfolio/chart", tags=["Portfolio"])
async def portfolio_chart(db: Session = Depends(get_db)):
    holdings = db.query(models.Holding).all()
    if not holdings:
        raise HTTPException(status_code=404, detail="Portfolio is empty.")
    return stock_service.get_portfolio_chart(holdings)


# ── MARKET DATA ───────────────────────────────────────────────────────────────

@app.get("/quote/{ticker}", response_model=schemas.StockQuote, tags=["Market Data"])
async def get_quote(ticker: str):
    quote = stock_service.get_full_quote(ticker.upper())
    if quote is None:
        raise HTTPException(status_code=404, detail=f"Could not fetch data for '{ticker}'.")
    return quote


@app.get("/history/{ticker}", response_model=List[schemas.PricePoint], tags=["Market Data"])
async def get_history(ticker: str, days: int = 30):
    if not 1 <= days <= 365:
        raise HTTPException(status_code=400, detail="days must be between 1 and 365.")
    history = stock_service.get_price_history(ticker.upper(), days)
    if not history:
        raise HTTPException(status_code=404, detail=f"No history found for '{ticker}'.")
    return history


@app.get("/metrics/{ticker}", response_model=schemas.StockMetrics, tags=["Market Data"])
async def get_metrics(ticker: str):
    metrics = stock_service.compute_metrics(ticker.upper())
    if metrics is None:
        raise HTTPException(status_code=404, detail=f"Could not compute metrics for '{ticker}'.")
    return metrics


@app.get("/news/{ticker}", tags=["Market Data"])
async def get_news(ticker: str):
    return stock_service.get_company_news(ticker.upper())


@app.get("/market/overview", tags=["Market Data"])
async def market_overview():
    return stock_service.get_market_overview()


@app.get("/candles/{ticker}", tags=["Market Data"])
async def get_candles(ticker: str, days: int = 30):
    if not 1 <= days <= 365:
        raise HTTPException(status_code=400, detail="days must be between 1 and 365.")
    data = stock_service.get_candles(ticker.upper(), days)
    if not data:
        raise HTTPException(status_code=404, detail=f"No candle data for '{ticker}'.")
    return data


# ── INTELLIGENCE ──────────────────────────────────────────────────────────────

@app.get("/portfolio/insights", tags=["Intelligence"])
async def portfolio_insights(db: Session = Depends(get_db)):
    """
    Analyses all holdings and returns actionable risk signals with confidence scores.
    Flags overbought positions, concentration risk, bearish crossovers,
    high volatility, and significant drawdowns.
    """
    holdings = db.query(models.Holding).all()
    if not holdings:
        raise HTTPException(status_code=404, detail="Portfolio is empty.")

    summary = stock_service.build_portfolio_summary(holdings)
    if not summary:
        raise HTTPException(status_code=503, detail="Could not fetch live prices.")

    enriched = []
    for h in summary.holdings:
        m = stock_service.compute_metrics(h.ticker)
        enriched.append({
            "ticker":        h.ticker,
            "current_value": h.current_value,
            "pnl_pct":       h.pnl_pct,
            "rsi_14":        m.rsi_14     if m else None,
            "ma_20":         m.ma_20      if m else None,
            "ma_50":         m.ma_50      if m else None,
            "volatility":    m.volatility if m else None,
        })

    return stock_service.generate_portfolio_insights(enriched)


@app.get("/portfolio/risk", tags=["Intelligence"])
async def portfolio_risk(db: Session = Depends(get_db)):
    """
    Aggregated risk profile: concentration score, average volatility,
    overbought/oversold counts, and overall risk rating.
    """
    holdings = db.query(models.Holding).all()
    if not holdings:
        raise HTTPException(status_code=404, detail="Portfolio is empty.")
    return stock_service.get_portfolio_risk(holdings)


@app.get("/portfolio/risk/decompose", tags=["Intelligence"])
async def portfolio_risk_decompose(db: Session = Depends(get_db)):
    """
    Factor risk decomposition: beta vs SPY, sector allocation,
    Herfindahl concentration score, plain-English summary.
    """
    holdings = db.query(models.Holding).all()
    if not holdings:
        raise HTTPException(status_code=404, detail="Portfolio is empty.")
    return stock_service.decompose_risk(holdings)


@app.get("/portfolio/stress-test/scenarios", tags=["Intelligence"])
async def stress_test_scenarios():
    """List all available stress test scenarios."""
    return stock_service.list_stress_scenarios()


@app.get("/portfolio/stress-test", tags=["Intelligence"])
async def stress_test(scenario: str = "market_crash_10pct", db: Session = Depends(get_db)):
    """
    Run a stress test against the portfolio.
    Query param: scenario (default: market_crash_10pct)
    """
    holdings = db.query(models.Holding).all()
    if not holdings:
        raise HTTPException(status_code=404, detail="Portfolio is empty.")
    result = stock_service.run_stress_test(holdings, scenario)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/sentiment/{ticker}", tags=["Intelligence"])
async def get_sentiment(ticker: str):
    """
    VADER sentiment analysis on recent news headlines.
    Returns sentiment_score (-1 to +1), label, and sample headlines.
    """
    return stock_service.get_sentiment(ticker.upper())


@app.get("/divergence/{ticker}", tags=["Intelligence"])
async def get_divergence(ticker: str):
    """
    Sentiment-price divergence signal.
    Compares VADER sentiment vs 10-day price return to surface divergence signals.
    """
    return stock_service.get_divergence(ticker.upper())