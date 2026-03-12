# Stock Portfolio Tracker API

A production-ready REST API for real-time equity portfolio management — built with FastAPI, SQLAlchemy, and Finnhub market data. Features a full-stack dashboard with live quotes, technical indicators, and P&L analytics.

**Live Demo:** https://stock-portfolio-api-qryi.onrender.com

---

## Features

- **Real-time quotes** — live prices, day change, market cap via Finnhub API
- **Price history** — 30-day OHLC chart per ticker
- **Technical indicators** — RSI-14, MA-20, MA-50, annualised volatility, trend signal
- **Portfolio management** — add/remove holdings, track cost basis
- **P&L analysis** — unrealised gain/loss per position and total portfolio
- **Interactive dashboard** — 3-column finance UI with live watchlist sidebar
- **CI/CD** — GitHub Actions test pipeline + auto-deploy on Render
- **Containerised** — Docker + docker-compose for local dev

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI |
| Database | SQLite (dev) / PostgreSQL (prod) |
| ORM | SQLAlchemy |
| Market Data | Finnhub API |
| Analytics | NumPy, Pandas |
| Testing | pytest |
| CI/CD | GitHub Actions |
| Deployment | Render (Docker) |

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Interactive dashboard UI |
| `GET` | `/health` | Health check |
| `POST` | `/portfolio` | Add a holding |
| `GET` | `/portfolio` | List all holdings |
| `PUT` | `/portfolio/{ticker}` | Update a holding |
| `DELETE` | `/portfolio/{ticker}` | Remove a holding |
| `GET` | `/portfolio/summary` | Full P&L breakdown at live prices |
| `GET` | `/quote/{ticker}` | Real-time quote |
| `GET` | `/history/{ticker}?days=30` | Price history |
| `GET` | `/metrics/{ticker}` | RSI-14, MA-20/50, volatility, trend |

---

## Local Setup

### Prerequisites
- Python 3.11+
- Finnhub API key (free at [finnhub.io](https://finnhub.io))

### Install & Run

```bash
git clone https://github.com/Divyansh21k/stock-portfolio-api
cd stock-portfolio-api

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Add your FINNHUB_API_KEY to .env

uvicorn app.main:app --reload
```

Open `http://localhost:8000`

### Run with Docker

```bash
docker-compose up --build
```

### Run Tests

```bash
pytest tests/ -v
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `FINNHUB_API_KEY` | Finnhub API key (required) |
| `DATABASE_URL` | PostgreSQL URL (optional, defaults to SQLite) |

---

## Project Structure

```
stock_portfolio_api/
├── app/
│   ├── main.py           # FastAPI routes
│   ├── database.py       # SQLAlchemy setup
│   ├── models.py         # ORM models
│   ├── schemas.py        # Pydantic schemas
│   ├── stock_service.py  # Market data + metrics
│   └── static/
│       └── index.html    # Dashboard UI
├── tests/
│   └── test_stock_service.py
├── .github/workflows/
│   └── ci.yml            # GitHub Actions pipeline
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Example Requests

```bash
# Real-time quote
curl https://stock-portfolio-api-qryi.onrender.com/quote/AAPL

# Add a holding
curl -X POST https://stock-portfolio-api-qryi.onrender.com/portfolio \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "shares": 10, "avg_buy_price": 175.00}'

# Portfolio P&L
curl https://stock-portfolio-api-qryi.onrender.com/portfolio/summary

# Technical indicators
curl https://stock-portfolio-api-qryi.onrender.com/metrics/NVDA
```

---

## Author

**Divyansh Kharnal**  
