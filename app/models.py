from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Holding(Base):
    __tablename__ = "holdings"

    id            = Column(Integer, primary_key=True, index=True)
    ticker        = Column(String(10), unique=True, index=True, nullable=False)
    shares        = Column(Float, nullable=False)
    avg_buy_price = Column(Float, nullable=False)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())