"""
Stock service — market data fetching and financial metric computation.
Uses yfinance (free, no API key required).
"""

import yfinance as yf
import numpy as np
from typing import Optional, List
from app import schemas


def get_current_price(ticker: str) -> Optional[float]:
    """Return latest price for a ticker, or None if not found."""
    try:
        info = yf.Ticker(ticker).fast_info
        price = info.last_price
        return round(float(price), 2) if price else None
    except Exception:
        return None


def get_full_quote(ticker: str) -> Optional[schemas.StockQuote]:
    """Return real-time quote: price, change, volume, market cap."""
    try:
        info = yf.Ticker(ticker).info
        current = info.get("currentPrice") or info.get("regularMarketPrice")
        prev    = info.get("previousClose") or info.get("regularMarketPreviousClose")
        volume  = info.get("volume") or info.get("regularMarketVolume", 0)
        mktcap  = info.get("marketCap")

        if not current or not prev:
            return None

        change     = round(current - prev, 4)
        change_pct = round((change / prev) * 100, 2)

        return schemas.StockQuote(
            ticker=ticker,
            current_price=round(current, 2),
            previous_close=round(prev, 2),
            change=change,
            change_pct=change_pct,
            volume=int(volume),
            market_cap=mktcap
        )
    except Exception:
        return None


def get_price_history(ticker: str, days: int = 30) -> List[schemas.PricePoint]:
    """Return daily closing prices for the past N days."""
    try:
        period = f"{days}d" if days <= 59 else f"{(days // 30) + 1}mo"
        df = yf.download(ticker, period=period, progress=False)[["Close"]].dropna()
        if df.empty:
            return []
        return [
            schemas.PricePoint(date=str(idx.date()), close=round(float(row["Close"]), 2))
            for idx, row in df.iterrows()
        ]
    except Exception:
        return []


def compute_metrics(ticker: str) -> Optional[schemas.StockMetrics]:
    """
    Compute technical indicators:
    - MA-20, MA-50 (Simple Moving Averages)
    - RSI-14 (Wilder's method)
    - 30-day annualised volatility (log-return std * sqrt(252))
    - Trend signal (Bullish/Bearish/Neutral)
    """
    try:
        df = yf.download(ticker, period="6mo", progress=False)
        if df.empty or len(df) < 20:
            return None

        closes = df["Close"].dropna()

        ma_20 = round(float(closes.rolling(20).mean().iloc[-1]), 2) if len(closes) >= 20 else None
        ma_50 = round(float(closes.rolling(50).mean().iloc[-1]), 2) if len(closes) >= 50 else None
        rsi   = _compute_rsi(closes)
        vol   = round(float(np.log(closes / closes.shift(1)).dropna().tail(30).std() * np.sqrt(252) * 100), 2)

        trend = None
        if ma_20 and ma_50:
            trend = "Bullish" if ma_20 > ma_50 else ("Bearish" if ma_20 < ma_50 else "Neutral")

        return schemas.StockMetrics(
            ticker=ticker, ma_20=ma_20, ma_50=ma_50,
            rsi_14=rsi, volatility=vol, trend=trend
        )
    except Exception:
        return None


def _compute_rsi(closes, period: int = 14) -> Optional[float]:
    """Wilder's RSI using exponential moving average of gains/losses."""
    try:
        delta    = closes.diff()
        gain     = delta.clip(lower=0)
        loss     = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
        rs       = avg_gain / avg_loss
        rsi      = 100 - (100 / (1 + rs))
        return round(float(rsi.iloc[-1]), 2)
    except Exception:
        return None


def build_portfolio_summary(holdings) -> Optional[schemas.PortfolioSummary]:
    """Fetch live prices and compute P&L for every holding in the portfolio."""
    rows = []
    total_cost = total_value = 0.0

    for h in holdings:
        price = get_current_price(h.ticker)
        if price is None:
            continue
        cost  = round(h.shares * h.avg_buy_price, 2)
        value = round(h.shares * price, 2)
        pnl   = round(value - cost, 2)
        pnl_pct = round((pnl / cost) * 100, 2) if cost else 0.0

        rows.append(schemas.HoldingSummary(
            ticker=h.ticker, shares=h.shares,
            avg_buy_price=h.avg_buy_price, current_price=price,
            cost_basis=cost, current_value=value,
            pnl=pnl, pnl_pct=pnl_pct
        ))
        total_cost  += cost
        total_value += value

    if not rows:
        return None

    total_pnl     = round(total_value - total_cost, 2)
    total_pnl_pct = round((total_pnl / total_cost) * 100, 2) if total_cost else 0.0

    return schemas.PortfolioSummary(
        total_cost_basis=round(total_cost, 2),
        total_current_value=round(total_value, 2),
        total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct,
        holdings=rows
    )
