"""Run: python -m scripts.debug_pool "What was Tesla's total revenue?" TSLA"""
import sys
from app.core.database import SessionLocal
from app.services.retrieval import hybrid_search, get_reranker

def main(query: str, ticker: str):
    with SessionLocal() as db:
        reranker = get_reranker()
        for pool in [30, 100, 300]:
            print(f"\n===== POOL SIZE: {pool} =====")
            # Pass k=pool so we get the full fused list back, not just the top 5
            cands = hybrid_search(db, query, k=pool, ticker=ticker, pool=pool)
            
            # Rerank the hybrid candidates
            if cands:
                scores = reranker.predict([(query, c["content"]) for c in cands])
                for c, s in zip(cands, scores):
                    c["rerank"] = round(float(s), 3)
                ranked_cands = sorted(cands, key=lambda r: r["rerank"], reverse=True)
            else:
                ranked_cands = []

            # Find all matches in the hybrid list (before reranking)
            matches_hybrid = [
                (i, c) for i, c in enumerate(cands) 
                if "94,827" in c["content"] or "94.83" in c["content"]
            ]
            total_matches = len(matches_hybrid)
            print(f"Total matching chunks found: {total_matches}")

            if not matches_hybrid:
                print("MISS: Target chunk not found in hybrid list.")
                continue

            # Find the first match in the reranked list
            rerank_rank = None
            rerank_score = None
            for i, c in enumerate(ranked_cands):
                if "94,827" in c["content"] or "94.83" in c["content"]:
                    rerank_rank = i
                    rerank_score = c["rerank"]
                    break

            # Use the best (lowest) hybrid rank from our matches
            best_hybrid_rank, best_match = matches_hybrid[0]
            
            print(f"Best Hybrid Rank: {best_hybrid_rank}")
            print(f"Rerank Rank: {rerank_rank} | Rerank Score: {rerank_score}")
            print(f"  snippet: {best_match['content'][:120].replace(chr(10), ' ')}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m scripts.debug_pool \"<query>\" <TICKER>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])