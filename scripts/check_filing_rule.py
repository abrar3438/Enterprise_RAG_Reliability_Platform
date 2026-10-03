"""Run: python -m scripts.check_filing_rule"""
from app.services.filings import resolve_filing_dates

tests = [
    ("What was Tesla's total revenue?", "TSLA"),
    ("What was Tesla's total revenue in 2025?", "TSLA"),
    ("What was Tesla's revenue in 2024?", "TSLA"),
    ("What was Apple's total revenue in fiscal 2025?", "AAPL"),
    ("What was Microsoft's net income in fiscal 2026?", "MSFT"),
    ("What were Apple's sales in 2023?", "AAPL"),
    ("What was ExxonMobil's total revenue in 2024?", None),
]
for q, t in tests:
    dates = resolve_filing_dates(q, t)
    print(t, "|", q, "->", [str(d) for d in dates] if dates else "all")