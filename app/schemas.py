from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime

class HoldingCreate(BaseModel):
    ticker: str          = Field(..., example="AAPL")
    shares: float        = Field(..., gt=0, example=10)
    avg_buy_price: float = Field(..., gt=0, example=150.00)
    @field_validator("ticker")
    @classmethod
    def uppercase_ticker(cls, v):
        return v.upper().strip()

class HoldingOut(BaseModel):
    id:            int
    ticker:        str
    shares:        float
    avg_buy_price: float
    created_at:    Optional[datetime] = None
    model_config = {"from_attributes": True}

class StockQuote(BaseModel):
    ticker:         str
    current_price:  float
    previous_close: float
    change:         float
    change_pct:     float
    volume:         int
    market_cap:     Optional[float] = None

class PricePoint(BaseModel):
    date:   str
    close:  float

class StockMetrics(BaseModel):
    ticker:     str
    ma_20:      Optional[float] = None
    ma_50:      Optional[float] = None
    rsi_14:     Optional[float] = None
    volatility: Optional[float] = None
    trend:      Optional[str]   = None

class HoldingSummary(BaseModel):
    ticker:        str
    shares:        float
    avg_buy_price: float
    current_price: float
    cost_basis:    float
    current_value: float
    pnl:           float
    pnl_pct:       float

class PortfolioSummary(BaseModel):
    total_cost_basis:    float
    total_current_value: float
    total_pnl:           float
    total_pnl_pct:       float
    holdings:            List[HoldingSummary]
