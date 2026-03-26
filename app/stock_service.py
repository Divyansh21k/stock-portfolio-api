"""
StockPulse — stock_service.py
Fixes: lazy API key init, TTL cache (price=15min, history=6hr),
       async httpx, operator precedence, VADER sentiment, divergence,
       stress test engine, factor risk decomposition.
"""

import os
import asyncio
import time
import httpx
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List
from app import schemas

# ── LAZY KEY ACCESS ───────────────────────────────────────────────────────────

def _fh_key() -> str:
    return os.getenv("FINNHUB_API_KEY", "")

def _av_key() -> str:
    return os.getenv("ALPHA_VANTAGE_KEY", "")

FINNHUB_BASE = "https://finnhub.io/api/v1"
AV_BASE      = "https://www.alphavantage.co/query"


# ── TTL CACHE ─────────────────────────────────────────────────────────────────

class _TTLCache:
    def __init__(self):
        self._store: dict = {}

    def get(self, key: str):
        entry = self._store.get(key)
        if entry and time.time() < entry["exp"]:
            return entry["val"]
        return None

    def set(self, key: str, val, ttl: int):
        self._store[key] = {"val": val, "exp": time.time() + ttl}

    def invalidate(self, key: str):
        self._store.pop(key, None)


_cache = _TTLCache()
PRICE_TTL   = 15 * 60       # 15 minutes
HISTORY_TTL = 6  * 60 * 60  # 6 hours
NEWS_TTL    = 30 * 60       # 30 minutes


# ── ASYNC HELPERS ─────────────────────────────────────────────────────────────

async def _fh_get(path: str, params: dict = {}) -> dict:
    params = {**params, "token": _fh_key()}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{FINNHUB_BASE}{path}", params=params)
        return r.json()


async def _av_get(params: dict) -> dict:
    params = {**params, "apikey": _av_key()}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(AV_BASE, params=params)
        return r.json()


def _run(coro):
    """Run async coroutine from sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ── QUOTES ────────────────────────────────────────────────────────────────────

async def _fetch_quote(ticker: str) -> Optional[dict]:
    try:
        d = await _fh_get("/quote", {"symbol": ticker})
        if not d or d.get("c", 0) == 0:
            return None
        return d
    except Exception:
        return None


def get_current_price(ticker: str) -> Optional[float]:
    cached = _cache.get(f"price:{ticker}")
    if cached is not None:
        return cached
    try:
        d = _run(_fetch_quote(ticker))
        if not d:
            return None
        price = round(float(d["c"]), 2)
        _cache.set(f"price:{ticker}", price, PRICE_TTL)
        return price
    except Exception:
        return None


def get_full_quote(ticker: str) -> Optional[schemas.StockQuote]:
    try:
        d = _run(_fetch_quote(ticker))
        if not d:
            return None
        current = round(float(d["c"]), 2)
        prev    = round(float(d["pc"]), 2)
        change  = round(float(d.get("d", current - prev)), 4)
        pct     = round(float(d.get("dp", (change / prev * 100) if prev else 0)), 2)

        async def _profile():
            return await _fh_get("/stock/profile2", {"symbol": ticker})

        profile = _run(_profile())
        mktcap  = profile.get("marketCapitalization", 0) * 1_000_000 if profile else None
        return schemas.StockQuote(
            ticker=ticker, current_price=current, previous_close=prev,
            change=change, change_pct=pct, volume=0, market_cap=mktcap
        )
    except Exception:
        return None


# ── ALPHA VANTAGE DAILY ───────────────────────────────────────────────────────

async def _fetch_av_daily(ticker: str) -> dict:
    data = await _av_get({
        "function":  "TIME_SERIES_DAILY",
        "symbol":    ticker,
        "outputsize": "compact"
    })
    if not isinstance(data, dict):
        return {}
    ts = data.get("Time Series (Daily)")
    return ts if isinstance(ts, dict) else {}


async def _fetch_fh_daily(ticker: str, days: int = 120) -> dict:
    now = datetime.utcnow()
    start = now - timedelta(days=days)
    data = await _fh_get("/stock/candle", {
        "symbol": ticker,
        "resolution": "D",
        "from": int(start.timestamp()),
        "to": int(now.timestamp())
    })
    if not isinstance(data, dict) or data.get("s") != "ok":
        return {}

    ts = {}
    stamps = data.get("t") or []
    opens = data.get("o") or []
    highs = data.get("h") or []
    lows = data.get("l") or []
    closes = data.get("c") or []
    volumes = data.get("v") or []
    count = min(len(stamps), len(opens), len(highs), len(lows), len(closes), len(volumes))
    for i in range(count):
        date_str = datetime.utcfromtimestamp(int(stamps[i])).strftime("%Y-%m-%d")
        ts[date_str] = {
            "1. open": str(opens[i]),
            "2. high": str(highs[i]),
            "3. low": str(lows[i]),
            "4. close": str(closes[i]),
            "5. volume": str(volumes[i]),
        }
    return ts


def _av_daily(ticker: str) -> dict:
    cached = _cache.get(f"av_daily:{ticker}")
    if cached is not None:
        return cached
    try:
        ts = _run(_fetch_av_daily(ticker))
        if not ts:
            ts = _run(_fetch_fh_daily(ticker))
        if ts:
            _cache.set(f"av_daily:{ticker}", ts, HISTORY_TTL)
        return ts or {}
    except Exception:
        return {}


# ── HISTORY ───────────────────────────────────────────────────────────────────

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
                "date":   date_str,
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

def compute_metrics(ticker: str) -> schemas.StockMetrics:
    default = schemas.StockMetrics(
        ticker=ticker, ma_20=0.0, ma_50=0.0, rsi_14=50.0, volatility=0.0, trend="Neutral"
    )
    try:
        ts = _av_daily(ticker)
        if not ts:
            return default

        closes = pd.Series([
            float(ts[d]["4. close"]) for d in sorted(ts.keys()) if "4. close" in ts[d]
        ], dtype=float).dropna()
        if closes.empty:
            return default

        latest_close = round(float(closes.iloc[-1]), 2)
        ma_20 = round(float(closes.rolling(20, min_periods=1).mean().iloc[-1]), 2) if len(closes) >= 1 else latest_close
        ma_50 = round(float(closes.rolling(50, min_periods=1).mean().iloc[-1]), 2) if len(closes) >= 1 else latest_close
        rsi = _compute_rsi(closes)
        if rsi is None:
            rsi = 50.0
        log_ret = np.log(closes / closes.shift(1)).dropna()
        vol = round(float(log_ret.tail(30).std() * np.sqrt(252) * 100), 2) if len(log_ret) >= 2 else 0.0
        trend = "Bullish" if ma_20 > ma_50 else ("Bearish" if ma_20 < ma_50 else "Neutral")
        return schemas.StockMetrics(ticker=ticker, ma_20=ma_20, ma_50=ma_50, rsi_14=rsi, volatility=vol, trend=trend)
    except Exception:
        return default


def _compute_rsi(closes: pd.Series, period: int = 14) -> Optional[float]:
    try:
        if len(closes) < period + 1:
            return None
        delta    = closes.diff()
        gain     = delta.clip(lower=0)
        loss     = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
        last_loss = float(avg_loss.iloc[-1])
        if last_loss == 0:
            return 100.0
        return round(100 - (100 / (1 + float(avg_gain.iloc[-1]) / last_loss)), 2)
    except Exception:
        return None


# ── NEWS ──────────────────────────────────────────────────────────────────────

def get_company_news(ticker: str):
    cached = _cache.get(f"news:{ticker}")
    if cached is not None:
        return cached

    async def _fetch():
        today     = datetime.utcnow().strftime("%Y-%m-%d")
        month_ago = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        data = await _fh_get("/company-news", {"symbol": ticker, "from": month_ago, "to": today})
        return data if isinstance(data, list) else []

    try:
        articles = _run(_fetch())
        result = [{
            "headline": a.get("headline", ""),
            "summary":  a.get("summary", ""),
            "url":      a.get("url", ""),
            "source":   a.get("source", ""),
            "datetime": a.get("datetime", 0)
        } for a in articles[:10] if a.get("headline")]
        _cache.set(f"news:{ticker}", result, NEWS_TTL)
        return result
    except Exception:
        return []


# ── MARKET OVERVIEW ───────────────────────────────────────────────────────────

def get_market_overview():
    symbols = [("SPY", "S&P 500 ETF"), ("QQQ", "NASDAQ ETF"), ("DIA", "Dow Jones ETF"), ("GLD", "Gold ETF")]

    async def _fetch_all():
        tasks = [_fh_get("/quote", {"symbol": sym}) for sym, _ in symbols]
        return await asyncio.gather(*tasks, return_exceptions=True)

    try:
        results = _run(_fetch_all())
        output = []
        for (sym, name), d in zip(symbols, results):
            if isinstance(d, Exception) or not d or d.get("c", 0) == 0:
                continue
            output.append({
                "symbol": sym, "name": name,
                "price":      round(float(d["c"]), 2),
                "change_pct": round(float(d["dp"]), 2)
            })
        return output
    except Exception:
        return []


# ── PORTFOLIO SUMMARY ─────────────────────────────────────────────────────────

def build_portfolio_summary(holdings) -> Optional[schemas.PortfolioSummary]:
    if not holdings:
        return None
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


# ── PORTFOLIO INSIGHTS ────────────────────────────────────────────────────────

def generate_portfolio_insights(holdings_with_metrics: list) -> dict:
    alerts = []
    def _safe_float(value, default=0.0):
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    total_value = sum(_safe_float(h.get("current_value"), 0.0) for h in holdings_with_metrics)

    for h in holdings_with_metrics:
        ticker  = h.get("ticker", "UNKNOWN")
        current_value = _safe_float(h.get("current_value"), 0.0)
        weight  = current_value / total_value if total_value else 0
        rsi     = _safe_float(h.get("rsi_14"), 50.0)
        ma_20   = _safe_float(h.get("ma_20"), 0.0)
        ma_50   = _safe_float(h.get("ma_50"), 0.0)
        vol     = _safe_float(h.get("volatility"), 0.0)
        pnl_pct = _safe_float(h.get("pnl_pct"), 0.0)
        signals = 0

        # Concentration risk
        if weight > 0.35:
            sev = "high" if weight > 0.45 else "medium"
            alerts.append({
                "ticker": ticker, "type": "concentration", "severity": sev,
                "message": f"{weight*100:.0f}% of portfolio in a single position — consider rebalancing",
                "confidence": "high"
            })
            signals += 1

        # RSI signals
        if rsi > 70:
            signals += 1
            alerts.append({
                "ticker": ticker, "type": "overbought", "severity": "high",
                "message": f"RSI at {rsi} — momentum suggests short-term pullback risk",
                "confidence": "high" if signals >= 3 else ("medium" if signals >= 2 else "low")
            })
        elif rsi < 30:
            signals += 1
            alerts.append({
                "ticker": ticker, "type": "oversold", "severity": "medium",
                "message": f"RSI at {rsi} — potential accumulation opportunity",
                "confidence": "high" if signals >= 3 else ("medium" if signals >= 2 else "low")
            })

        # Bearish crossover
        if ma_20 > 0 and ma_50 > 0 and ma_20 < ma_50 * 0.97:
            signals += 1
            alerts.append({
                "ticker": ticker, "type": "bearish_cross", "severity": "medium",
                "message": f"MA-20 (${ma_20}) below MA-50 (${ma_50}) — bearish momentum signal",
                "confidence": "high" if signals >= 3 else ("medium" if signals >= 2 else "low")
            })

        # High volatility
        if vol > 50:
            signals += 1
            alerts.append({
                "ticker": ticker, "type": "high_volatility", "severity": "medium",
                "message": f"Annualised volatility at {vol}% — elevated risk profile",
                "confidence": "high" if signals >= 3 else ("medium" if signals >= 2 else "low")
            })

        # Large unrealised loss
        if pnl_pct < -15:
            signals += 1
            alerts.append({
                "ticker": ticker, "type": "drawdown", "severity": "high",
                "message": f"Position down {abs(pnl_pct):.1f}% from cost basis — review thesis",
                "confidence": "high" if signals >= 3 else ("medium" if signals >= 2 else "low")
            })

    high   = [a for a in alerts if a["severity"] == "high"]
    medium = [a for a in alerts if a["severity"] == "medium"]

    if len(high) >= 2:
        summary = f"{len(high)} high-priority alerts. Immediate review recommended."
    elif len(high) == 1:
        summary = "1 high-priority alert. Portfolio requires attention."
    elif medium:
        summary = f"{len(medium)} medium-priority signals. Portfolio is within acceptable risk bounds."
    else:
        summary = "No significant risk signals detected. Portfolio appears well-balanced."

    return {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "alert_count":  {"high": len(high), "medium": len(medium), "total": len(alerts)},
        "summary": summary,
        "alerts":  alerts
    }


# ── PORTFOLIO RISK ────────────────────────────────────────────────────────────

def get_portfolio_risk(holdings) -> dict:
    if not holdings:
        return {}

    total_value = 0
    vols, rsis = [], []
    most_volatile = {"ticker": None, "volatility": 0}
    overbought_count = oversold_count = 0

    prices = {h.ticker: get_current_price(h.ticker) for h in holdings}

    for h in holdings:
        price = prices.get(h.ticker)
        if not price:
            continue
        total_value += h.shares * price
        m = compute_metrics(h.ticker)
        if m:
            if m.volatility:
                vols.append(m.volatility)
                if m.volatility > most_volatile["volatility"]:
                    most_volatile = {"ticker": h.ticker, "volatility": m.volatility}
            if m.rsi_14:
                rsis.append(m.rsi_14)
                if m.rsi_14 > 70: overbought_count += 1
                if m.rsi_14 < 30: oversold_count   += 1

    weights = []
    for h in holdings:
        price = prices.get(h.ticker)
        if price and total_value:
            weights.append((h.shares * price) / total_value)
    concentration = round(sum(w ** 2 for w in weights), 3)

    avg_vol = round(sum(vols) / len(vols), 1) if vols else None

    # Fixed operator precedence
    if (avg_vol and avg_vol > 45) or concentration > 0.4:
        risk_rating = "High"
    elif (avg_vol and avg_vol > 25) or concentration > 0.25:
        risk_rating = "Medium"
    else:
        risk_rating = "Low"

    risk_summary_map = {
        "High":   "Portfolio shows elevated concentration and/or volatility. Consider diversification.",
        "Medium": "Portfolio has moderate risk exposure. Monitor high-volatility positions.",
        "Low":    "Portfolio is well-diversified with manageable volatility levels."
    }

    return {
        "generated_at":        datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "risk_rating":         risk_rating,
        "risk_summary":        risk_summary_map[risk_rating],
        "concentration_score": concentration,
        "avg_volatility":      avg_vol,
        "most_volatile":       most_volatile["ticker"],
        "overbought_count":    overbought_count,
        "oversold_count":      oversold_count,
        "position_count":      len(holdings)
    }


# ── VADER SENTIMENT ───────────────────────────────────────────────────────────

def get_sentiment(ticker: str) -> dict:
    cached = _cache.get(f"sentiment:{ticker}")
    if cached is not None:
        return cached

    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()
    except ImportError:
        return {"error": "vaderSentiment not installed"}

    news = get_company_news(ticker)
    if not news:
        result = {
            "ticker": ticker, "sentiment_score": 0.0,
            "sentiment_label": "Neutral", "headline_count": 0,
            "sample_headlines": []
        }
        _cache.set(f"sentiment:{ticker}", result, NEWS_TTL)
        return result

    scores = []
    headlines = []
    for article in news[:20]:
        headline = article.get("headline", "")
        if not headline:
            continue
        score = analyzer.polarity_scores(headline)["compound"]
        scores.append(score)
        headlines.append({"headline": headline, "score": round(score, 4)})

    mean_score = round(sum(scores) / len(scores), 4) if scores else 0.0

    if mean_score >= 0.05:
        label = "Positive"
    elif mean_score <= -0.05:
        label = "Negative"
    else:
        label = "Neutral"

    result = {
        "ticker":           ticker,
        "sentiment_score":  mean_score,
        "sentiment_label":  label,
        "headline_count":   len(scores),
        "sample_headlines": headlines[:5]
    }
    _cache.set(f"sentiment:{ticker}", result, NEWS_TTL)
    return result


# ── SENTIMENT-PRICE DIVERGENCE ────────────────────────────────────────────────

def get_divergence(ticker: str) -> dict:
    cached = _cache.get(f"divergence:{ticker}")
    if cached is not None:
        return cached

    sentiment = get_sentiment(ticker)
    sentiment_score = sentiment.get("sentiment_score", 0.0)

    # 10-day price return from AV history
    ts = _av_daily(ticker)
    price_return_10d = None
    if ts and len(ts) >= 11:
        dates  = sorted(ts.keys())
        close_now  = float(ts[dates[-1]]["4. close"])
        close_10d  = float(ts[dates[-11]]["4. close"])
        price_return_10d = round((close_now - close_10d) / close_10d * 100, 2)

    if price_return_10d is None:
        result = {
            "ticker": ticker, "signal": "Insufficient Data",
            "divergence_score": 0.0, "sentiment_score": sentiment_score,
            "price_return_10d": None, "interpretation": "Not enough price history."
        }
        return result

    # Normalise: sentiment in [-1,1], price return as fraction
    price_norm = price_return_10d / 100.0
    divergence_score = round(sentiment_score - price_norm, 4)

    sentiment_bullish = sentiment_score > 0.05
    sentiment_bearish = sentiment_score < -0.05
    price_bullish     = price_return_10d > 1.0
    price_bearish     = price_return_10d < -1.0

    if sentiment_bullish and price_bearish:
        signal = "Bullish Divergence"
        interpretation = "News sentiment is positive but price has fallen — potential recovery ahead."
    elif sentiment_bearish and price_bullish:
        signal = "Bearish Divergence"
        interpretation = "News sentiment is negative despite price gains — possible correction risk."
    elif sentiment_bullish and price_bullish:
        signal = "Confirmed Bullish"
        interpretation = "Positive sentiment and rising price — momentum appears sustainable."
    elif sentiment_bearish and price_bearish:
        signal = "Confirmed Bearish"
        interpretation = "Negative sentiment and falling price — avoid adding to position."
    else:
        signal = "Neutral"
        interpretation = "No significant divergence between sentiment and price action."

    result = {
        "ticker":           ticker,
        "signal":           signal,
        "divergence_score": divergence_score,
        "sentiment_score":  sentiment_score,
        "price_return_10d": price_return_10d,
        "interpretation":   interpretation
    }
    _cache.set(f"divergence:{ticker}", result, NEWS_TTL)
    return result


# ── STRESS TEST ENGINE ────────────────────────────────────────────────────────

STRESS_SCENARIOS = {
    "market_crash_10pct": {
        "name":        "Market Crash -10%",
        "description": "Broad equity selloff of 10% across all holdings.",
        "shocks":      {"_default": -0.10}
    },
    "rbi_rate_hike": {
        "name":        "RBI Rate Hike (+50bps)",
        "description": "Rate-sensitive sectors (financials, real estate) hit hardest.",
        "shocks":      {
            "HDFCBANK.NS": -0.07, "ICICIBANK.NS": -0.07, "SBIN.NS": -0.08,
            "AXISBANK.NS": -0.07, "_default": -0.03
        }
    },
    "fii_outflow": {
        "name":        "FII Outflow Shock",
        "description": "Foreign institutional selling triggers broad India market decline.",
        "shocks":      {"_default": -0.06, "NIFTY": -0.08}
    },
    "it_sector_shock": {
        "name":        "IT Sector Shock (-15%)",
        "description": "US recession fears trigger a major correction in IT exporters.",
        "shocks":      {
            "INFY": -0.15, "TCS.NS": -0.15, "WIPRO.NS": -0.14,
            "HCLTECH.NS": -0.14, "TECHM.NS": -0.15,
            "INFY.NS": -0.15, "_default": -0.04
        }
    },
    "us_recession": {
        "name":        "US Recession",
        "description": "S&P 500 falls 20%. Global risk-off, commodities and emerging markets sell off.",
        "shocks":      {
            "AAPL": -0.22, "MSFT": -0.20, "GOOGL": -0.21, "AMZN": -0.22,
            "NVDA": -0.28, "META": -0.22, "TSLA": -0.30,
            "SPY":  -0.20, "QQQ":  -0.25,
            "_default": -0.15
        }
    }
}


def run_stress_test(holdings, scenario_key: str) -> dict:
    if scenario_key not in STRESS_SCENARIOS:
        return {"error": f"Unknown scenario '{scenario_key}'. Use /portfolio/stress-test/scenarios to list valid options."}

    scenario  = STRESS_SCENARIOS[scenario_key]
    shocks    = scenario["shocks"]
    results   = []
    total_current = total_stressed = 0.0

    for h in holdings:
        price = get_current_price(h.ticker)
        if price is None:
            continue
        shock = shocks.get(h.ticker, shocks.get("_default", -0.05))
        stressed_price = round(price * (1 + shock), 2)
        current_val    = round(h.shares * price, 2)
        stressed_val   = round(h.shares * stressed_price, 2)
        impact         = round(stressed_val - current_val, 2)
        impact_pct     = round(shock * 100, 1)
        total_current  += current_val
        total_stressed += stressed_val
        results.append({
            "ticker":        h.ticker,
            "current_value": current_val,
            "stressed_value": stressed_val,
            "impact":        impact,
            "shock_pct":     impact_pct
        })

    total_impact     = round(total_stressed - total_current, 2)
    total_impact_pct = round((total_impact / total_current * 100) if total_current else 0, 2)

    return {
        "scenario":          scenario_key,
        "scenario_name":     scenario["name"],
        "description":       scenario["description"],
        "generated_at":      datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_current_value":  round(total_current, 2),
        "total_stressed_value": round(total_stressed, 2),
        "total_impact":         total_impact,
        "total_impact_pct":     total_impact_pct,
        "holdings":             results
    }


def list_stress_scenarios() -> list:
    return [
        {"key": k, "name": v["name"], "description": v["description"]}
        for k, v in STRESS_SCENARIOS.items()
    ]


# ── FACTOR RISK DECOMPOSITION ─────────────────────────────────────────────────

SECTOR_MAP = {
    "AAPL": "Technology",  "MSFT": "Technology",  "GOOGL": "Technology",
    "GOOG": "Technology",  "NVDA": "Technology",  "META": "Technology",
    "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
    "JPM":  "Financials",  "BAC":  "Financials",  "GS":   "Financials",
    "JNJ":  "Healthcare",  "PFE":  "Healthcare",  "MRK":  "Healthcare",
    "XOM":  "Energy",      "CVX":  "Energy",
    "SPY":  "Broad Market","QQQ":  "Broad Market",
    "INFY": "Technology",  "TCS.NS": "Technology", "WIPRO.NS": "Technology",
    "HDFCBANK.NS": "Financials", "ICICIBANK.NS": "Financials",
    "RELIANCE.NS": "Energy", "SBIN.NS": "Financials",
}


def decompose_risk(holdings) -> dict:
    if not holdings:
        return {}

    benchmark = "SPY"
    benchmark_ts = _av_daily(benchmark)

    total_value = 0
    betas       = {}
    sector_alloc: dict = {}
    prices = {h.ticker: get_current_price(h.ticker) for h in holdings}

    for h in holdings:
        price = prices.get(h.ticker)
        if not price:
            continue
        val = h.shares * price
        total_value += val

    for h in holdings:
        price = prices.get(h.ticker)
        if not price or not total_value:
            continue

        weight = (h.shares * price) / total_value
        sector = SECTOR_MAP.get(h.ticker, "Other")
        sector_alloc[sector] = round(sector_alloc.get(sector, 0) + weight * 100, 1)

        # Beta calculation (60-day rolling correlation with SPY)
        ticker_ts = _av_daily(h.ticker)
        if ticker_ts and benchmark_ts and len(ticker_ts) >= 60 and len(benchmark_ts) >= 60:
            try:
                t_dates = sorted(ticker_ts.keys())[-60:]
                b_dates = sorted(benchmark_ts.keys())[-60:]
                common  = sorted(set(t_dates) & set(b_dates))[-60:]
                if len(common) >= 30:
                    t_closes = pd.Series([float(ticker_ts[d]["4. close"]) for d in common])
                    b_closes = pd.Series([float(benchmark_ts[d]["4. close"]) for d in common])
                    t_ret    = t_closes.pct_change().dropna()
                    b_ret    = b_closes.pct_change().dropna()
                    if b_ret.var() > 0:
                        beta = round(float(np.cov(t_ret, b_ret)[0][1] / b_ret.var()), 2)
                        betas[h.ticker] = beta
            except Exception:
                pass

    # Herfindahl score
    weights = []
    for h in holdings:
        price = prices.get(h.ticker)
        if price and total_value:
            weights.append((h.shares * price) / total_value)
    herfindahl = round(sum(w ** 2 for w in weights), 3)

    avg_beta = round(sum(betas.values()) / len(betas), 2) if betas else None
    max_beta_ticker = max(betas, key=betas.get) if betas else None

    # Plain English summary
    parts = []
    if avg_beta:
        if avg_beta > 1.3:
            parts.append(f"Portfolio is highly aggressive (avg beta {avg_beta}x vs SPY) — amplifies market moves significantly.")
        elif avg_beta > 1.0:
            parts.append(f"Portfolio is moderately aggressive (avg beta {avg_beta}x vs SPY).")
        else:
            parts.append(f"Portfolio is relatively defensive (avg beta {avg_beta}x vs SPY).")
    if herfindahl > 0.4:
        parts.append("Concentration is very high — single-stock risk is elevated.")
    elif herfindahl > 0.25:
        parts.append("Moderate concentration. Consider spreading across more positions.")
    else:
        parts.append("Concentration looks healthy across positions.")

    top_sector = max(sector_alloc, key=sector_alloc.get) if sector_alloc else None
    if top_sector:
        parts.append(f"Largest sector exposure: {top_sector} ({sector_alloc[top_sector]:.0f}%).")

    return {
        "generated_at":        datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "benchmark":           benchmark,
        "avg_beta":            avg_beta,
        "beta_by_ticker":      betas,
        "most_volatile_beta":  max_beta_ticker,
        "herfindahl_score":    herfindahl,
        "sector_allocation":   sector_alloc,
        "plain_english_summary": " ".join(parts) if parts else "Insufficient data for full decomposition."
    }
