import pytest
import pandas as pd
from app.stock_service import _compute_rsi, build_portfolio_summary


def series(values):
    return pd.Series(values, dtype=float)


class MockHolding:
    def __init__(self, ticker, shares, buy_price):
        self.ticker = ticker
        self.shares = shares
        self.avg_buy_price = buy_price


def test_rsi_overbought():
    prices = series([100 + i * 2 for i in range(30)])
    assert _compute_rsi(prices) > 70


def test_rsi_oversold():
    prices = series([200 - i * 3 for i in range(30)])
    assert _compute_rsi(prices) < 30


def test_rsi_always_in_range():
    prices = series([100, 102, 98, 105, 97, 110, 95, 115, 90, 120,
                     85, 118, 88, 112, 92, 108, 96, 104, 100, 103])
    rsi = _compute_rsi(prices)
    assert rsi is not None
    assert 0 <= rsi <= 100


def test_rsi_insufficient_data_returns_none():
    assert _compute_rsi(series([100, 101, 102]), period=14) is None


def test_empty_portfolio_returns_none():
    assert build_portfolio_summary([]) is None


def test_pnl_gain(monkeypatch):
    from app import stock_service
    monkeypatch.setattr(stock_service, "get_current_price",
                        lambda t: {"AAPL": 200.0, "MSFT": 300.0}.get(t))
    summary = build_portfolio_summary([
        MockHolding("AAPL", 10, 150.0),
        MockHolding("MSFT", 5,  250.0),
    ])
    assert summary.total_cost_basis    == 2750.0
    assert summary.total_current_value == 3500.0
    assert summary.total_pnl           == 750.0


def test_pnl_loss(monkeypatch):
    from app import stock_service
    monkeypatch.setattr(stock_service, "get_current_price", lambda t: 80.0)
    summary = build_portfolio_summary([MockHolding("TSLA", 10, 100.0)])
    assert summary.total_pnl     == -200.0
    assert summary.total_pnl_pct == -20.0


def test_unavailable_ticker_skipped(monkeypatch):
    from app import stock_service
    monkeypatch.setattr(stock_service, "get_current_price",
                        lambda t: 100.0 if t == "AAPL" else None)
    summary = build_portfolio_summary([
        MockHolding("AAPL", 5, 80.0),
        MockHolding("FAKE", 10, 50.0),
    ])
    assert len(summary.holdings) == 1
    assert summary.holdings[0].ticker == "AAPL"