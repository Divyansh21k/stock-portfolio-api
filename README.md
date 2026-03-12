# 📈 Stock Portfolio Tracker API

> Real-time equity portfolio management powered by Finnhub market data and AI-driven technical analysis.

**Live Demo:** https://stock-portfolio-api-qryi.onrender.com

---

## About

Stock Portfolio Tracker is a production-ready REST API and interactive dashboard for managing equity portfolios with live market data. Built with FastAPI and powered by the Finnhub API for real-time quotes, it gives you instant access to technical indicators, P&L analytics, and price history — all in one place.

---

## Why Stock Portfolio Tracker?

- ⚡ **Real-time Data** — Live quotes and price history via Finnhub API
- 📊 **Technical Analysis** — RSI-14, MA-20/50, volatility and trend signals computed on the fly
- 💼 **Portfolio Management** — Track holdings, cost basis, and unrealised P&L
- 🚀 **Production Ready** — Dockerised, CI/CD via GitHub Actions, deployed on Render
- 🌐 **Full Stack** — Interactive dashboard UI included, no external frontend needed

---

## ✨ Features

### 📉 Market Data
- Real-time stock quotes with day change and market cap
- 30-day price history with interactive chart
- Support for US equities and Indian stocks (NSE/BSE)

### 🧮 Technical Indicators
- **RSI-14** — Overbought / Oversold signal with visual gauge
- **MA-20 & MA-50** — Moving average crossover analysis
- **Annualised Volatility** — 30-day rolling volatility
- **Trend Signal** — Bullish / Bearish / Neutral classification

### 💰 Portfolio Analytics
- Add, update, and remove holdings
- Live cost basis vs market value comparison
- Unrealised P&L per position and total portfolio return
- Full position breakdown table

### 🖥️ Interactive Dashboard
- 3-column finance UI with live watchlist sidebar
- Portfolio value card with real-time P&L
- Clock with NYSE market hours indicator

---

## 🛠️ Tech Stack

**Backend**
- FastAPI — REST API framework
- SQLAlchemy — ORM
- PostgreSQL (prod) / SQLite (dev)
- Finnhub API — Market data

**Data & Analytics**
- NumPy — Volatility and returns computation
- Pandas — Time-series processing

**DevOps**
- Docker + docker-compose
- GitHub Actions — CI pipeline
- Render — Cloud deployment

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Interactive dashboard |
| `GET` | `/health` | Health check |
| `POST` | `/portfolio` | Add a holding |
| `GET` | `/portfolio` | List all holdings |
| `PUT` | `/portfolio/{ticker}` | Update a holding |
| `DELETE` | `/portfolio/{ticker}` | Remove a holding |
| `GET` | `/portfolio/summary` | Full P&L at live prices |
| `GET` | `/quote/{ticker}` | Real-time quote |
| `GET` | `/history/{ticker}?days=30` | Price history |
| `GET` | `/metrics/{ticker}` | RSI, MA, volatility, trend |

---

## 🚀 Local Setup

### Prerequisites
- Python 3.11+
- Finnhub API key — free at [finnhub.io](https://finnhub.io)

### Install & Run

```bash
git clone https://github.com/Divyansh21k/stock-portfolio-api
cd stock-portfolio-api

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Add FINNHUB_API_KEY to .env

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

## 🔐 Environment Variables

| Variable | Description |
|---|---|
| `FINNHUB_API_KEY` | Finnhub API key (required) |
| `DATABASE_URL` | PostgreSQL URL (optional, defaults to SQLite) |

---

## 📁 Project Structure

```
stock_portfolio_api/
├── app/
│   ├── main.py              # FastAPI routes
│   ├── database.py          # SQLAlchemy setup
│   ├── models.py            # ORM models
│   ├── schemas.py           # Pydantic schemas
│   ├── stock_service.py     # Market data + metrics
│   └── static/
│       └── index.html       # Dashboard UI
├── tests/
│   └── test_stock_service.py
├── .github/workflows/
│   └── ci.yml               # GitHub Actions
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

Made with ❤️ by [Divyansh Kharnal](https://github.com/Divyansh21k)
