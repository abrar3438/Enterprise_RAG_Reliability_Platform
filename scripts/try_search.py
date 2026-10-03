# """Run: python -m scripts.try_search "your question" [TICKER]"""
# import sys

# from app.core.database import SessionLocal
# from app.services.retrieval import bm25_search, dense_search, hybrid_search, rerank_search

# q = sys.argv[1]
# ticker = sys.argv[2] if len(sys.argv) > 2 else None

# with SessionLocal() as db:
#     for name, results in [
#         ("DENSE", dense_search(db, q, ticker=ticker)),
#         ("BM25", bm25_search(q, ticker=ticker)),
#         ("HYBRID", hybrid_search(db, q, ticker=ticker)),
#         ("RERANK", rerank_search(db, q, ticker=ticker)),
#     ]:
#         print(f"\n===== {name} =====")
#         for r in results:
#             print(f"{r['ticker']} {r['filing_date']} [{r['section'][:35]}]")
#             print("   ", r["content"][:1200].replace("\n", " "), "\n")

"""Run: python -m scripts.try_search "your question" [TICKER]"""
import sys

from app.core.database import SessionLocal
from app.services.retrieval import rerank_search

q = sys.argv[1]
ticker = sys.argv[2] if len(sys.argv) > 2 else None

with SessionLocal() as db:
    for r in rerank_search(db, q, ticker=ticker):
        print(f"{r['rerank']}  {r['ticker']} {r['filing_date']} [{r['section'][:35]}]")
        print("   ", r["content"][:1200].replace("\n", " "), "\n")