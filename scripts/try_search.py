"""Run: python -m scripts.try_search "your question" [TICKER]"""
import sys

from app.core.database import SessionLocal
from app.services.retrieval import dense_search

with SessionLocal() as db:
    for r in dense_search(db, sys.argv[1], ticker=sys.argv[2] if len(sys.argv) > 2 else None):
        print(f"{r['distance']}  {r['ticker']} {r['filing_date']}  [{r['section'][:40]}]")
        print("   ", r["content"][:250].replace("\n", " "), "\n")