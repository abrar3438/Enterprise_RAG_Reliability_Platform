"""Run: python -m scripts.run_eval --mode all --label baseline"""
import argparse
import json
import os
from datetime import datetime
from app.core.database import SessionLocal
from app.services.retrieval import dense_search, bm25_search, hybrid_search, rerank_search

def is_hit(entry, result):
    # If entry expects a specific filing, chunk must come from it
    if entry.get("filing_date"):
        if str(result.get("filing_date", "")) != entry["filing_date"]:
            return False
    # Must contain at least one snippet
    content = result.get("content", "")
    snippets = entry.get("evidence_snippet", [])
    if isinstance(snippets, str):
        snippets = [snippets]
    return any(s in content for s in snippets)

def get_rank(entry, results, k):
    for i, r in enumerate(results[:k]):
        if is_hit(entry, r):
            return i + 1
    return None

def run_mode(mode, golden_set, db, k=10, pool=100):
    results_log = []
    hits_at_1 = 0
    hits_at_5 = 0
    mrr_sum = 0
    total = 0
    
    num_h5, num_tot = 0, 0
    nar_h5, nar_tot = 0, 0
    misses = []

    for entry in golden_set:
        if entry.get("type") == "not_found":
            continue
            
        total += 1
        ticker = entry.get("ticker")
        query = entry["question"]
        q_type = entry["type"]
        
        if mode == "dense":
            res = dense_search(db, query, k=k, ticker=ticker)
        elif mode == "bm25":
            res = bm25_search(query, k=k, ticker=ticker)
        elif mode == "hybrid":
            res = hybrid_search(db, query, k=k, ticker=ticker, pool=pool)
        elif mode == "rerank":
            res = rerank_search(db, query, k=k, ticker=ticker, pool=pool)
        else:
            raise ValueError(f"Unknown mode: {mode}")

        rank = get_rank(entry, res, k)
        
        if q_type == "numeric":
            num_tot += 1
            if rank and rank <= 5: num_h5 += 1
        elif q_type == "narrative":
            nar_tot += 1
            if rank and rank <= 5: nar_h5 += 1

        if rank == 1: hits_at_1 += 1
        if rank and rank <= 5: hits_at_5 += 1
        if rank: mrr_sum += 1.0 / rank
        else: misses.append(entry["id"])
            
        top5 = [{
            "ticker": r.get("ticker"),
            "filing_date": str(r.get("filing_date")),
            "section": (r.get("section") or "")[:35],
            "content": (r.get("content") or "")[:400].replace("\n", " ")  # Changed to 400 for better diagnosis
        } for r in res[:5]]
        
        results_log.append({
            "id": entry["id"],
            "type": q_type,
            "rank": rank,
            "top_5": top5
        })

    h1 = hits_at_1 / total if total else 0
    h5 = hits_at_5 / total if total else 0
    mrr = mrr_sum / total if total else 0
    num_h5_ratio = num_h5 / num_tot if num_tot else 0
    nar_h5_ratio = nar_h5 / nar_tot if nar_tot else 0

    metrics = {
        "hit_at_1": h1,
        "hit_at_5": h5,
        "mrr": mrr,
        "numeric_hit_at_5": num_h5_ratio,
        "narrative_hit_at_5": nar_h5_ratio,
        "misses": misses
    }

    print(f"\n===== Mode: {mode.upper()} =====")
    print(f"Hit@1: {hits_at_1}/{total} ({h1:.2f})")
    print(f"Hit@5: {hits_at_5}/{total} ({h5:.2f})")
    print(f"MRR: {mrr:.3f}")
    print(f"Numeric Hit@5: {num_h5}/{num_tot} ({num_h5_ratio:.2f})")
    print(f"Narrative Hit@5: {nar_h5}/{nar_tot} ({nar_h5_ratio:.2f})")
    print(f"Misses: {', '.join(misses) if misses else 'None'}")
    
    return results_log, metrics

def run_not_found(golden_set, db, k=10, pool=100):
    print("\n===== Not Found Entries (Rerank, no ticker) =====")
    not_found_log = []
    for entry in golden_set:
        if entry.get("type") != "not_found":
            continue
        query = entry["question"]
        res = rerank_search(db, query, k=k, ticker=None, pool=pool)
        if res:
            top = res[0]
            score = top.get("rerank", 0)
            text = (top.get("content") or "")[:150].replace("\n", " ")  # Left at 150 for not_found
            print(f"[{entry['id']}] Top Score: {score:.3f}")
            print(f"  Text: {text}")
            not_found_log.append({
                "id": entry["id"],
                "top_score": score,
                "top_text": text
            })
        else:
            print(f"[{entry['id']}] No results returned.")
            not_found_log.append({
                "id": entry["id"],
                "top_score": None,
                "top_text": None
            })
    return not_found_log

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden-set", default="eval/golden_set.json")
    parser.add_argument("--mode", default="all", choices=["dense", "bm25", "hybrid", "rerank", "all"])
    parser.add_argument("--label", default="run")
    args = parser.parse_args()

    with open(args.golden_set, "r", encoding="utf-8") as f:
        golden_set = json.load(f)

    os.makedirs("eval/results", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"eval/results/{timestamp}_{args.label}.json"

    k = 10
    pool = 100
    modes = ["dense", "bm25", "hybrid", "rerank"] if args.mode == "all" else [args.mode]

    all_logs = {
        "settings": {"k": k, "pool": pool, "modes": modes},
        "metrics": {},
        "results": {},
        "not_found": []
    }

    with SessionLocal() as db:
        for mode in modes:
            res_log, metrics = run_mode(mode, golden_set, db, k=k, pool=pool)
            all_logs["results"][mode] = res_log
            all_logs["metrics"][mode] = metrics
            
            # Save after each mode to prevent data loss on crash
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(all_logs, f, indent=2)
        
        if args.mode in ["all", "rerank"]:
            nf_log = run_not_found(golden_set, db, k=k, pool=pool)
            all_logs["not_found"] = nf_log
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(all_logs, f, indent=2)

    # Print combined summary table
    print("\n===== SUMMARY TABLE =====")
    print(f"{'Mode':<10} | {'Hit@1':<6} | {'Hit@5':<6} | {'MRR':<6} | {'Num H@5':<8} | {'Nar H@5':<8}")
    print("-" * 60)
    for mode in modes:
        m = all_logs["metrics"].get(mode, {})
        print(f"{mode.upper():<10} | {m.get('hit_at_1', 0):<6.2f} | {m.get('hit_at_5', 0):<6.2f} | {m.get('mrr', 0):<6.3f} | {m.get('numeric_hit_at_5', 0):<8.2f} | {m.get('narrative_hit_at_5', 0):<8.2f}")
    
    print(f"\nResults saved to {output_file}")

if __name__ == "__main__":
    main()