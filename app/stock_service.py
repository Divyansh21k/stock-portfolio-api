"""
Stock service — market data via Finnhub API (quotes) + Yahoo Finance v8 (history/metrics).
"""

import os
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List
from app import schemas

FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "")
FINNHUB_BASE = "https://finnhub.io/api/v1"

_fh = requests.Session()
_fh.headers.update({"X-Finnhub-Token": FINNHUB_KEY})

_yf = requests.Session()
_yf.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
})


def get_full_quote(ticker: str) -> Optional[schemas.StockQuote]:
    try:
        r = _fh.get(f"{FINNHUB_BASE}/quote", params={"symbol": ticker}, timeout=10)
        data = r.json()
        if not data or data.get("c", 0) == 0:
            return None
        current = round(float(data["c"]), 2)
        prev    = round(float(data["pc"]), 2)
        change  = round(float(data["d"]) if data.get("d") else current - prev, 4)
        pct     = round(float(data["dp"]) if data.get("dp") else (change / prev * 100 if prev else 0), 2)
        profile = _fh.get(f"{FINNHUB_BASE}/stock/profile2", params={"symbol": ticker}, timeout=10).json()
        mktcap  = profile.get("marketCapitalization", 0) * 1_000_000 if profile else None
        return schemas.StockQuote(
            ticker=ticker, current_price=current, previous_close=prev,
            change=change, change_pct=pct, volume=0, market_cap=mktcap
        )
    except Exception:
        return None


def get_current_price(ticker: str) -> Optional[float]:
    try:
        r = _fh.get(f"{FINNHUB_BASE}/quote", params={"symbol": ticker}, timeout=10)
        data = r.json()
        if not data or data.get("c", 0) == 0:
            return None
        return round(float(data["c"]), 2)
    except Exception:
        return None


def _yahoo_history(ticker: str, days: int) -> list:
    end   = int(datetime.utcnow().timestamp())
    start = int((datetime.utcnow() - timedelta(days=days + 10)).timestamp())
    for base in ["https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"]:
        try:
            r = _yf.get(f"{base}/v8/finance/chart/{ticker}",
                params={"period1": start, "period2": end, "interval": "1d", "includePrePost": "false"},
                timeout=15)
            if r.status_code == 200:
                result = r.json().get("chart", {}).get("result", [])
                if result:
                    return result[0]
        except Exception:
            continue
    return []


def get_price_history(ticker: str, days: int = 30) -> List[schemas.PricePoint]:
    try:
        result = _yahoo_history(ticker, days)
        if not result:
            return []
        timestamps = result.get("timestamp", [])
        closes     = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        points = []
        for t, c in zip(timestamps, closes):
            if c is None:
                continue
            points.append(schemas.PricePoint(
                date=datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"),
                close=round(float(c), 2)
            ))
        return points[-days:]
    except Exception:
        return []


def compute_metrics(ticker: str) -> Optional[schemas.StockMetrics]:
    try:
        result = _yahoo_history(ticker, 200)
        if not result:
            return None
        raw = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        closes = pd.Series([c for c in raw if c is not None], dtype=float)
        if len(closes) < 20:
            return None
        ma_20   = round(float(closes.rolling(20).mean().iloc[-1]), 2) if len(closes) >= 20 else None
        ma_50   = round(float(closes.rolling(50).mean().iloc[-1]), 2) if len(closes) >= 50 else None
        rsi     = _compute_rsi(closes)
        log_ret = np.log(closes / closes.shift(1)).dropna()
        vol     = round(float(log_ret.tail(30).std() * np.sqrt(252) * 100), 2) if len(log_ret) >= 5 else None
        trend   = None
        if ma_20 and ma_50:
            trend = "Bullish" if ma_20 > ma_50 else ("Bearish" if ma_20 < ma_50 else "Neutral")
        return schemas.StockMetrics(ticker=ticker, ma_20=ma_20, ma_50=ma_50, rsi_14=rsi, volatility=vol, trend=trend)
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
            ticker=h.ticker, shares=h.shares, avg_buy_price=h.avg_buy_price,
            current_price=price, cost_basis=cost, current_value=value, pnl=pnl, pnl_pct=pnl_pct
        ))
        total_cost  += cost
        total_value += value
    if not rows:
        return None
    total_pnl     = round(total_value - total_cost, 2)
    total_pnl_pct = round((total_pnl / total_cost) * 100, 2) if total_cost else 0.0
    return schemas.PortfolioSummary(
        total_cost_basis=round(total_cost, 2), total_current_value=round(total_value, 2),
        total_pnl=total_pnl, total_pnl_pct=total_pnl_pct, holdings=rows
    )
