"""Company detection for query routing."""
import re

COMPANIES = [
    {"ticker": "AAPL", "aliases": ["apple", "aapl"]},
    {"ticker": "MSFT", "aliases": ["microsoft", "msft"]},
    {"ticker": "NVDA", "aliases": ["nvidia", "nvda"]},
    {"ticker": "TSLA", "aliases": ["tesla", "tsla"]},
    {"ticker": "WMT", "aliases": ["walmart", "wal-mart", "wal mart", "wmt"]},
    {"ticker": "JPM", "aliases": ["jpmorgan chase", "jpmorgan", "jp morgan", "jpmorganchase", "chase", "jpm"]},
    {"ticker": "PFE", "aliases": ["pfizer", "pfe"]},
]

# whole-word match; lookarounds also work for aliases with hyphens or spaces
_PATTERNS = [
    (c["ticker"], [re.compile(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])") for a in c["aliases"]])
    for c in COMPANIES
]


def detect_ticker(question: str) -> dict:
    """Return {'ticker': str | None, 'status': 'single' | 'zero' | 'multiple'}."""
    q = (question or "").lower()
    found = {ticker for ticker, patterns in _PATTERNS if any(p.search(q) for p in patterns)}
    if len(found) == 1:
        return {"ticker": next(iter(found)), "status": "single"}
    return {"ticker": None, "status": "zero" if not found else "multiple"}