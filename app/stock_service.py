"""
Stock service — market data fetching and financial metric computation.
Uses yfinance (free, no API key required).
Uses .history() instead of .info dict for reliability on cloud servers.
"""

import yfinance as yf
import numpy as np
import pandas as pd
from typing import Optional, List
from app import schemas


def _flatten_close(df) -> pd.Series:
    """Handle both single and multi-level column DataFrames from yfinance."""
    if df.empty:
        return pd.Series(dtype=float)
    if isinstance(df.columns, pd.MultiIndex):
        if "Close" in df.columns.get_level_values(0):
            col = df["Close"]
            return col.iloc[:, 0].dropna() if isinstance(col, pd.DataFrame) else col.dropna()
    if "Close" in df.columns:
        return df["Close"].dropna()
    return pd.Series(dtype=float)


def get_current_price(ticker: str) -> Optional[float]:
    """Return latest price for a ticker, or None if not found."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        closes = _flatten_close(hist)
        if not closes.empty:
            return round(float(closes.iloc[-1]), 2)
        return None
    except Exception:
        return None


def get_full_quote(ticker: str) -> Optional[schemas.StockQuote]:
    """Return real-time quote using history() for reliability on cloud."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        closes = _flatten_close(hist)

        if closes.empty or len(closes) < 2:
            return None

        current = round(float(closes.iloc[-1]), 2)
        prev    = round(float(closes.iloc[-2]), 2)

        volume = 0
        mktcap = None
        try:
            fi = t.fast_info
            volume = int(getattr(fi, 'three_month_average_volume', 0) or 0)
            mktcap = getattr(fi, 'market_cap', None)
        except Exception:
            pass

        change     = round(current - prev, 4)
        change_pct = round((change / prev) * 100, 2) if prev else 0.0

        return schemas.StockQuote(
            ticker=ticker,
            current_price=current,
            previous_close=prev,
            change=change,
            change_pct=change_pct,
            volume=volume,
            market_cap=mktcap
        )
    except Exception:
        return None


def get_price_history(ticker: str, days: int = 30) -> List[schemas.PricePoint]:
    """Return daily closing prices for the past N days."""
    try:
        t = yf.Ticker(ticker)
        period = f"{days}d" if days <= 59 else f"{(days // 30) + 1}mo"
        df = t.history(period=period)
        closes = _flatten_close(df)
        if closes.empty:
            return []
        result = []
        for idx, val in closes.items():
            try:
                date_str = idx.date().isoformat() if hasattr(idx, 'date') else str(idx)[:10]
                result.append(schemas.PricePoint(date=date_str, close=round(float(val), 2)))
            except Exception:
                continue
        return result
    except Exception:
        return []


def compute_metrics(ticker: str) -> Optional[schemas.StockMetrics]:
    """Technical indicators: MA-20, MA-50, RSI-14, volatility, trend."""
    try:
        t = yf.Ticker(ticker)
        df = t.history(period="6mo")
        closes = _flatten_close(df)

        if closes.empty or len(closes) < 20:
            return None

        ma_20 = round(float(closes.rolling(20).mean().iloc[-1]), 2) if len(closes) >= 20 else None
        ma_50 = round(float(closes.rolling(50).mean().iloc[-1]), 2) if len(closes) >= 50 else None
        rsi   = _compute_rsi(closes)
        log_ret = np.log(closes / closes.shift(1)).dropna()
        vol   = round(float(log_ret.tail(30).std() * np.sqrt(252) * 100), 2) if len(log_ret) >= 5 else None

        trend = None
        if ma_20 and ma_50:
            trend = "Bullish" if ma_20 > ma_50 else ("Bearish" if ma_20 < ma_50 else "Neutral")

        return schemas.StockMetrics(
            ticker=ticker, ma_20=ma_20, ma_50=ma_50,
            rsi_14=rsi, volatility=vol, trend=trend
        )
    except Exception:
        return None


def _compute_rsi(closes: pd.Series, period: int = 14) -> Optional[float]:
    try:
        if len(closes) < period + 1:
            return None
        delta    = closes.diff()
        gain     = delta.clip(lower=0)
        loss     = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
        last_loss = float(avg_loss.iloc[-1])
        if last_loss == 0:
            return 100.0
        rs = float(avg_gain.iloc[-1]) / last_loss
        return round(100 - (100 / (1 + rs)), 2)
    except Exception:
        return None


def build_portfolio_summary(holdings) -> Optional[schemas.PortfolioSummary]:
    """Fetch live prices and compute P&L for every holding."""
    rows = []
    total_cost = total_value = 0.0

    for h in holdings:
        price = get_current_price(h.ticker)
        if price is None:
            continue
        cost    = round(h.shares * h.avg_buy_price, 2)
        value   = round(h.shares * price, 2)
        pnl     = round(value - cost, 2)
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