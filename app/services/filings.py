"""Which filing(s) a question should search. Pure Python: no DB, no models."""
import re
from datetime import date

# ticker -> {the company's own fiscal-year label: filing date}
FILINGS: dict[str, dict[int, date]] = {
    "AAPL": {2025: date(2025, 10, 31), 2024: date(2024, 11, 1)},
    "MSFT": {2026: date(2026, 7, 29), 2025: date(2025, 7, 30)},
    "NVDA": {2026: date(2026, 2, 25), 2025: date(2025, 2, 26)},
    "JPM": {2025: date(2026, 2, 13)},
    "PFE": {2025: date(2026, 2, 26), 2024: date(2025, 2, 27)},
    "WMT": {2026: date(2026, 3, 13), 2025: date(2025, 3, 14)},
    "TSLA": {2025: date(2026, 1, 29), 2024: date(2025, 1, 30)},
}

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def resolve_filing_dates(query: str, ticker: str | None) -> list[date] | None:
    """Return the filing dates to search, or None for no restriction.
    Uses only the question text and the ticker (never the golden entry)."""
    if not ticker:
        return None
    labels = FILINGS.get(ticker.upper())
    if not labels:
        return None
    years = {int(y) for y in _YEAR_RE.findall(query)}
    matched = sorted({labels[y] for y in years if y in labels}, reverse=True)
    if matched:
        return matched
    if years:  # a year was named but we hold no filing for it: search all
        return sorted(labels.values(), reverse=True)
    return [max(labels.values())]  # no year: newest filing only