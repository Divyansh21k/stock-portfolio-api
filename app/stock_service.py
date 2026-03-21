"""
Stock service — yfinance for quotes, history, and metrics.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional, List
from app import schemas


def get_full_quote(ticker: str) -> Optional[schemas.StockQuote]:
    try:
        clean = ticker.upper()
        stock = yf.Ticker(clean)
        # fast_info is faster for basic quotes, available in yfinance 0.2+
        info = stock.fast_info
        if not info or 'last_price' not in info:
            # fallback to history if fast_info fails
            hist = stock.history(period="1d")
            if hist.empty:
                return None
            current = round(float(hist['Close'].iloc[-1]), 2)
            prev    = round(float(info.get('previous_close', current)) if info else current, 2)
            vol     = int(hist['Volume'].iloc[-1])
            mktcap  = info.get('market_cap', 0) if info else 0
        else:
            current = round(float(info['last_price']), 2)
            prev    = round(float(info.get('previous_close', current)), 2)
            vol     = int(info.get('last_volume', 0))
            mktcap  = info.get('market_cap', 0)

        change  = round(current - prev, 4)
        pct     = round((change / prev * 100) if prev else 0, 2)
        
        return schemas.StockQuote(
            ticker=clean,
            current_price=current,
            previous_close=prev,
            change=change,
            change_pct=pct,
            volume=vol,
            market_cap=mktcap
        )
    except Exception:
        return None


def get_current_price(ticker: str) -> Optional[float]:
    try:
        stock = yf.Ticker(ticker.upper())
        info = stock.fast_info
        if info and 'last_price' in info:
            return round(float(info['last_price']), 2)
        hist = stock.history(period="1d")
        if not hist.empty:
            return round(float(hist['Close'].iloc[-1]), 2)
        return None
    except Exception:
        return None


def get_price_history(ticker: str, days: int = 30) -> List[schemas.PricePoint]:
    try:
        # TradingView wants OHLCV data with a timestamp.
        stock = yf.Ticker(ticker.upper())
        # Provide enough calendar days to get at least `days` trading days
        start = (datetime.utcnow() - timedelta(days=days + days//2 + 10)).strftime("%Y-%m-%d")
        hist = stock.history(start=start)
        if hist.empty:
            return []
        
        points = []
        for index, row in hist.iterrows():
            date_str = index.strftime("%Y-%m-%d")
            points.append(schemas.PricePoint(
                date=date_str,
                time=date_str,
                open=round(float(row['Open']), 2),
                high=round(float(row['High']), 2),
                low=round(float(row['Low']), 2),
                close=round(float(row['Close']), 2),
                volume=int(row['Volume'])
            ))
        return points[-days:]
    except Exception:
        return []


def compute_metrics(ticker: str) -> Optional[schemas.StockMetrics]:
    try:
        stock = yf.Ticker(ticker.upper())
        hist = stock.history(period="1y")
        if hist.empty or len(hist) < 20:
            return None
        
        closes = hist['Close']
        ma_20 = round(float(closes.rolling(20).mean().iloc[-1]), 2) if len(closes) >= 20 else None
        ma_50 = round(float(closes.rolling(50).mean().iloc[-1]), 2) if len(closes) >= 50 else None
        
        rsi = _compute_rsi(closes)
        
        log_ret = np.log(closes / closes.shift(1)).dropna()
        vol = round(float(log_ret.tail(30).std() * np.sqrt(252) * 100), 2) if len(log_ret) >= 5 else None
        
        trend = None
        if ma_20 and ma_50:
            trend = "Bullish" if ma_20 > ma_50 else ("Bearish" if ma_20 < ma_50 else "Neutral")
            
        return schemas.StockMetrics(
            ticker=ticker.upper(),
            ma_20=ma_20,
            ma_50=ma_50,
            rsi_14=rsi,
            volatility=vol,
            trend=trend
        )
    except Exception:
        return None


def _compute_rsi(closes: pd.Series, period: int = 14) -> Optional[float]:
    try:
        if len(closes) < period + 1:
            return None
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
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
        cost = round(h.shares * h.avg_buy_price, 2)
        value = round(h.shares * price, 2)
        pnl = round(value - cost, 2)
        pnl_pct = round((pnl / cost) * 100, 2) if cost else 0.0
        rows.append(schemas.HoldingSummary(
            ticker=h.ticker, shares=h.shares, avg_buy_price=h.avg_buy_price,
            current_price=price, cost_basis=cost, current_value=value, pnl=pnl, pnl_pct=pnl_pct
        ))
        total_cost += cost
        total_value += value
        
    if not rows:
        return None
        
    total_pnl = round(total_value - total_cost, 2)
    total_pnl_pct = round((total_pnl / total_cost) * 100, 2) if total_cost else 0.0
    
    return schemas.PortfolioSummary(
        total_cost_basis=round(total_cost, 2),
        total_current_value=round(total_value, 2),
        total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct,
        holdings=rows
    )

import os
import requests
FINNHUB_BASE = "https://finnhub.io/api/v1"
try:
    _fh = requests.Session()
    _fh.params.update({"token": os.getenv("FINNHUB_API_KEY", "")})
except Exception:
    pass

# 1. Company news via Finnhub
def get_company_news(ticker: str):
    from datetime import datetime, timedelta
    today = datetime.utcnow().strftime("%Y-%m-%d")
    month_ago = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    r = _fh.get(f"{FINNHUB_BASE}/company-news",
        params={"symbol": ticker, "from": month_ago, "to": today},
        timeout=10)
    if r.status_code != 200:
        return []
    articles = r.json()[:10]
    return [{
        "headline": a.get("headline", ""),
        "summary": a.get("summary", ""),
        "url": a.get("url", ""),
        "source": a.get("source", ""),
        "datetime": a.get("datetime", 0)
    } for a in articles if a.get("headline")]

# 2. Market overview via Finnhub quotes
def get_market_overview():
    symbols = [
        ("SPY", "S&P 500 ETF"),
        ("QQQ", "NASDAQ ETF"),
        ("DIA", "Dow Jones ETF"),
        ("GLD", "Gold ETF"),
    ]
    result = []
    for sym, name in symbols:
        try:
            r = _fh.get(f"{FINNHUB_BASE}/quote",
                params={"symbol": sym}, timeout=8)
            d = r.json()
            if d.get("c", 0) != 0:
                result.append({
                    "symbol": sym,
                    "name": name,
                    "price": round(float(d["c"]), 2),
                    "change_pct": round(float(d["dp"]), 2)
                })
        except:
            continue
    return result

# 3. Candlestick data via Alpha Vantage
def get_candles(ticker: str, days: int = 30):
    import os
    import requests
    AV_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")
    try:
        r = requests.get("https://www.alphavantage.co/query", params={
            "function": "TIME_SERIES_DAILY",
            "symbol": ticker,
            "outputsize": "compact",
            "apikey": AV_KEY
        }, timeout=15)
        data = r.json()
        ts = data.get("Time Series (Daily)", {})
        if not ts:
            return []
        candles = []
        for date_str in sorted(ts.keys())[-days:]:
            v = ts[date_str]
            candles.append({
                "date": date_str,
                "open": round(float(v["1. open"]), 2),
                "high": round(float(v["2. high"]), 2),
                "low": round(float(v["3. low"]), 2),
                "close": round(float(v["4. close"]), 2),
                "volume": int(v["5. volume"])
            })
        return candles
    except:
        return []

# 4. Portfolio value over time
def get_portfolio_chart(holdings, days: int = 30):
    from collections import defaultdict
    daily_totals = defaultdict(float)
    for h in holdings:
        history = get_price_history(h.ticker, days)
        for point in history:
            daily_totals[point.date] += round(h.shares * point.close, 2)
    return [{"date": d, "value": round(v, 2)}
            for d, v in sorted(daily_totals.items())]
