"""
Stock service — market data via Finnhub API.
Finnhub works reliably on all cloud providers (no IP blocks).
Set FINNHUB_API_KEY environment variable on Render.
"""

import os
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List
from app import schemas

FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "")
BASE = "https://finnhub.io/api/v1"

_sess = requests.Session()
_sess.headers.update({"X-Finnhub-Token": FINNHUB_KEY})


def _get(path: str, params: dict = {}) -> Optional[dict]:
    try:
        r = _sess.get(f"{BASE}{path}", params=params, timeout=10)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def get_full_quote(ticker: str) -> Optional[schemas.StockQuote]:
    data = _get("/quote", {"symbol": ticker})
    if not data or data.get("c", 0) == 0:
        return None
    current = round(float(data["c"]), 2)
    prev    = round(float(data["pc"]), 2)
    change  = round(float(data["d"]), 4)
    pct     = round(float(data["dp"]), 2)

    profile = _get("/stock/profile2", {"symbol": ticker})
    mktcap  = None
    if profile and profile.get("marketCapitalization"):
        mktcap = profile["marketCapitalization"] * 1_000_000

    return schemas.StockQuote(
        ticker=ticker,
        current_price=current,
        previous_close=prev,
        change=change,
        change_pct=pct,
        volume=0,
        market_cap=mktcap
    )


def get_current_price(ticker: str) -> Optional[float]:
    data = _get("/quote", {"symbol": ticker})
    if not data or data.get("c", 0) == 0:
        return None
    return round(float(data["c"]), 2)


def get_price_history(ticker: str, days: int = 30) -> List[schemas.PricePoint]:
    to_ts   = int(datetime.utcnow().timestamp())
    from_ts = int((datetime.utcnow() - timedelta(days=days + 5)).timestamp())

    data = _get("/stock/candle", {
        "symbol": ticker,
        "resolution": "D",
        "from": from_ts,
        "to": to_ts
    })

    if not data or data.get("s") != "ok":
        return []

    result = []
    for t, c in zip(data["t"], data["c"]):
        try:
            date_str = datetime.utcfromtimestamp(t).strftime("%Y-%m-%d")
            result.append(schemas.PricePoint(date=date_str, close=round(float(c), 2)))
        except Exception:
            continue
    return result[-days:]


def compute_metrics(ticker: str) -> Optional[schemas.StockMetrics]:
    to_ts   = int(datetime.utcnow().timestamp())
    from_ts = int((datetime.utcnow() - timedelta(days=200)).timestamp())

    data = _get("/stock/candle", {
        "symbol": ticker,
        "resolution": "D",
        "from": from_ts,
        "to": to_ts
    })

    if not data or data.get("s") != "ok" or len(data["c"]) < 20:
        return None

    closes = pd.Series(data["c"], dtype=float)

    ma_20 = round(float(closes.rolling(20).mean().iloc[-1]), 2) if len(closes) >= 20 else None
    ma_50 = round(float(closes.rolling(50).mean().iloc[-1]), 2) if len(closes) >= 50 else None
    rsi   = _compute_rsi(closes)

    log_ret = np.log(closes / closes.shift(1)).dropna()
    vol     = round(float(log_ret.tail(30).std() * np.sqrt(252) * 100), 2) if len(log_ret) >= 5 else None

    trend = None
    if ma_20 and ma_50:
        trend = "Bullish" if ma_20 > ma_50 else ("Bearish" if ma_20 < ma_50 else "Neutral")

    return schemas.StockMetrics(
        ticker=ticker, ma_20=ma_20, ma_50=ma_50,
        rsi_14=rsi, volatility=vol, trend=trend
    )


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