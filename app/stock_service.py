"""
Stock service — Finnhub (quotes) + Alpha Vantage (candles) + yfinance fallback removed.
"""

import os
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List
from app import schemas

FINNHUB_KEY  = os.getenv("FINNHUB_API_KEY", "")
FINNHUB_BASE = "https://finnhub.io/api/v1"
AV_KEY       = os.getenv("ALPHA_VANTAGE_KEY", "")

_fh = requests.Session()
_fh.headers.update({"X-Finnhub-Token": FINNHUB_KEY})


# ── QUOTES ────────────────────────────────────────────────────────────────────

def get_full_quote(ticker: str) -> Optional[schemas.StockQuote]:
    try:
        r = _fh.get(f"{FINNHUB_BASE}/quote", params={"symbol": ticker}, timeout=10)
        d = r.json()
        if not d or d.get("c", 0) == 0:
            return None
        current = round(float(d["c"]), 2)
        prev    = round(float(d["pc"]), 2)
        change  = round(float(d.get("d", current - prev)), 4)
        pct     = round(float(d.get("dp", (change/prev*100) if prev else 0)), 2)
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
        d = r.json()
        if not d or d.get("c", 0) == 0:
            return None
        return round(float(d["c"]), 2)
    except Exception:
        return None


# ── HISTORY (Alpha Vantage) ───────────────────────────────────────────────────

def _av_daily(ticker: str) -> dict:
    try:
        r = requests.get("https://www.alphavantage.co/query", params={
            "function": "TIME_SERIES_DAILY",
            "symbol": ticker,
            "outputsize": "compact",
            "apikey": AV_KEY
        }, timeout=15)
        return r.json().get("Time Series (Daily)", {})
    except Exception:
        return {}


def get_price_history(ticker: str, days: int = 30) -> List[schemas.PricePoint]:
    try:
        ts = _av_daily(ticker)
        if not ts:
            return []
        points = []
        for date_str in sorted(ts.keys())[-days:]:
            v = ts[date_str]
            points.append(schemas.PricePoint(
                date=date_str,
                close=round(float(v["4. close"]), 2)
            ))
        return points
    except Exception:
        return []


# ── CANDLES ───────────────────────────────────────────────────────────────────

def get_candles(ticker: str, days: int = 30):
    try:
        ts = _av_daily(ticker)
        if not ts:
            return []
        candles = []
        for date_str in sorted(ts.keys())[-days:]:
            v = ts[date_str]
            candles.append({
                "date": date_str,
                "open":   round(float(v["1. open"]), 2),
                "high":   round(float(v["2. high"]), 2),
                "low":    round(float(v["3. low"]), 2),
                "close":  round(float(v["4. close"]), 2),
                "volume": int(v["5. volume"])
            })
        return candles
    except Exception:
        return []


# ── METRICS ───────────────────────────────────────────────────────────────────

def compute_metrics(ticker: str) -> Optional[schemas.StockMetrics]:
    try:
        ts = _av_daily(ticker)
        if not ts or len(ts) < 20:
            return None
        closes = pd.Series([float(ts[d]["4. close"]) for d in sorted(ts.keys())], dtype=float)
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
        delta     = closes.diff()
        gain      = delta.clip(lower=0)
        loss      = -delta.clip(upper=0)
        avg_gain  = gain.ewm(alpha=1/period, min_periods=period).mean()
        avg_loss  = loss.ewm(alpha=1/period, min_periods=period).mean()
        last_loss = float(avg_loss.iloc[-1])
        if last_loss == 0:
            return 100.0
        return round(100 - (100 / (1 + float(avg_gain.iloc[-1]) / last_loss)), 2)
    except Exception:
        return None


# ── NEWS ──────────────────────────────────────────────────────────────────────

def get_company_news(ticker: str):
    try:
        today      = datetime.utcnow().strftime("%Y-%m-%d")
        month_ago  = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        r = _fh.get(f"{FINNHUB_BASE}/company-news",
            params={"symbol": ticker, "from": month_ago, "to": today}, timeout=10)
        if r.status_code != 200:
            return []
        return [{
            "headline": a.get("headline", ""),
            "summary":  a.get("summary", ""),
            "url":      a.get("url", ""),
            "source":   a.get("source", ""),
            "datetime": a.get("datetime", 0)
        } for a in r.json()[:10] if a.get("headline")]
    except Exception:
        return []


# ── MARKET OVERVIEW ───────────────────────────────────────────────────────────

def get_market_overview():
    symbols = [("SPY","S&P 500 ETF"),("QQQ","NASDAQ ETF"),("DIA","Dow Jones ETF"),("GLD","Gold ETF")]
    result  = []
    for sym, name in symbols:
        try:
            d = _fh.get(f"{FINNHUB_BASE}/quote", params={"symbol": sym}, timeout=8).json()
            if d.get("c", 0) != 0:
                result.append({"symbol": sym, "name": name,
                    "price": round(float(d["c"]), 2), "change_pct": round(float(d["dp"]), 2)})
        except Exception:
            continue
    return result


# ── PORTFOLIO SUMMARY ─────────────────────────────────────────────────────────

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


# ── PORTFOLIO CHART ───────────────────────────────────────────────────────────

def get_portfolio_chart(holdings, days: int = 30):
    from collections import defaultdict
    daily_totals = defaultdict(float)
    for h in holdings:
        for point in get_price_history(h.ticker, days):
            daily_totals[point.date] += round(h.shares * point.close, 2)
    return [{"date": d, "value": round(v, 2)} for d, v in sorted(daily_totals.items())]
