# StockPulse — Equity Risk & Insight Engine

> Turns raw market data into actionable portfolio intelligence. Built for investors who want Bloomberg-level risk signals without the Bloomberg price tag.

**Live Demo:** https://stock-portfolio-api-qryi.onrender.com  
**API Docs:** https://stock-portfolio-api-qryi.onrender.com/docs

---

## What it does

StockPulse is a production-deployed REST API that tracks equity portfolios in real time and surfaces meaningful risk signals — not just raw numbers. It tells you *what the data means*, not just what it is.

```json
GET /portfolio/insights

{
  "generated_at": "2026-03-23T14:30:00Z",
  "alert_count": { "high": 1, "medium": 2, "total": 3 },
  "summary": "1 high-priority alert. Portfolio requires attention.",
  "alerts": [
    {
      "ticker": "NVDA",
      "type": "overbought",
      "severity": "high",
      "message": "RSI at 78.4 — momentum suggests short-term pullback risk"
    },
    {
      "ticker": "AAPL",
      "type": "concentration",
      "severity": "medium",
      "message": "42% of portfolio in a single position — consider rebalancing"
    }
  ]
}
```

---

## Architecture

```
Client → FastAPI → Finnhub API (live quotes)
                 → Alpha Vantage (price history, OHLCV)
                 → PostgreSQL (portfolio state)
                 → Insight Engine (rules-based risk analysis)
```

---

## Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/portfolio/insights` | Actionable risk alerts per holding |
| `GET` | `/portfolio/risk` | Aggregated risk profile with concentration score |
| `GET` | `/portfolio/summary` | Full P&L at live prices |
| `GET` | `/portfolio/chart` | Portfolio value over time |
| `GET` | `/quote/{ticker}` | Real-time quote via Finnhub |
| `GET` | `/candles/{ticker}` | OHLCV candlestick data via Alpha Vantage |
| `GET` | `/metrics/{ticker}` | RSI-14, MA-20/50, volatility, trend signal |
| `GET` | `/news/{ticker}` | Latest company news via Finnhub |
| `GET` | `/market/overview` | Live index overview (SPY, QQQ, DIA, GLD) |
| `POST` | `/portfolio` | Add a holding |
| `DELETE` | `/portfolio/{ticker}` | Remove a holding |

---

## Insight Engine

The insight layer converts raw technical indicators into plain-English risk signals using rule-based logic:

| Signal | Trigger | Severity |
|---|---|---|
| Overbought | RSI > 70 | High |
| Oversold | RSI < 30 | Medium |
| Concentration risk | Single position > 35% of portfolio | High/Medium |
| Bearish crossover | MA-20 < MA-50 × 0.97 | Medium |
| High volatility | Annualised vol > 50% | Medium |
| Drawdown alert | Position down > 15% from cost | High |

Risk rating is computed using a **Herfindahl concentration score** combined with average portfolio volatility.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | Python, FastAPI |
| Database | PostgreSQL (prod), SQLite (dev) |
| ORM | SQLAlchemy |
| Market Data | Finnhub API, Alpha Vantage |
| Analytics | NumPy, Pandas |
| Deployment | Docker, GitHub Actions CI, Render |

---

## Local Setup

```bash
git clone https://github.com/Divyansh21k/stock-portfolio-api
cd stock-portfolio-api
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add FINNHUB_API_KEY + ALPHA_VANTAGE_KEY
uvicorn app.main:app --reload
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `FINNHUB_API_KEY` | [finnhub.io](https://finnhub.io) — free tier |
| `ALPHA_VANTAGE_KEY` | [alphavantage.co](https://www.alphavantage.co) — free tier |
| `DATABASE_URL` | PostgreSQL connection string (defaults to SQLite) |

---

## Author

**Divyansh Kharnal** — B.Tech CS, Manipal University Jaipur  
[GitHub](https://github.com/Divyansh21k) · [LinkedIn](https://linkedin.com/in/divyanshkharnal)
