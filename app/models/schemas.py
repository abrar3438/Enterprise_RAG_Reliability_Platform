"""Pydantic schemas for the API request and response."""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

VALID_TICKERS = {"AAPL", "MSFT", "NVDA", "TSLA", "WMT", "JPM", "PFE"}


class Citation(BaseModel):
    number: int
    ticker: Optional[str] = None
    filing_date: Optional[str] = None
    section: Optional[str] = None
    preview: Optional[str] = None


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    ticker: Optional[str] = None

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("ticker", mode="before")
    @classmethod
    def clean_ticker(cls, v):
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("ticker must be a string")
        v = v.strip().upper()
        if not v:
            return None
        if v not in VALID_TICKERS:
            raise ValueError(f"Invalid ticker. Must be one of: {', '.join(sorted(VALID_TICKERS))}")
        return v


class QueryResponse(BaseModel):
    answer: str
    refused: bool
    citations: List[Citation]
    ticker_used: Optional[str] = None
    ticker_source: str  # "request", "detected" or "none"
    latency_ms: int  # whole request
    retrieval_ms: int = 0
    cost_bdt: Optional[float] = None
    prompt_version: str
    model: str
    warning: Optional[str] = None
    cache_hit: bool = False