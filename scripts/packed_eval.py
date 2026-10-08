"""Run: python -m scripts.packed_eval --baseline eval/results/<rerank_run>.json --budget 6000 --label packed

Scores two systems with the SAME scorer as scripts/run_eval.py on the same queries:
  prod:   rerank_search k=10 (exactly as run_eval.py), ranks scored up to 10
  packed: top 5 of that same rerank result, packed with pack(), blocks scored
The --baseline file must be the saved run_eval output whose rerank metrics are
the reference (the widened-JPM run, hit@5 0.62, MRR 0.503). If prod does not
reproduce those metrics, the comparison is invalid and the script says so."""
import argparse
import json
import os
from datetime import datetime

from app.core.database import SessionLocal
from app.services.packing import pack, split_header
from app.services.retrieval import rerank_search

K = 10          # same as run_eval.py main()
PACK_TOP_N = 10  # production returns 5 chunks to the prompt
POOL = 100


def is_hit(entry, result):
    """Identical to scripts/run_eval.py. Keep in sync."""
    if entry.get("filing_date"):
        if str(result.get("filing_date", "")) != entry["filing_date"]:
            return False
    content = result.get("content", "")
    snippets = entry.get("evidence_snippet", [])
    if isinstance(snippets, str):
        snippets = [snippets]
    return any(s in content for s in snippets)


def get_rank(entry, results, k):
    """Identical to scripts/run_eval.py."""
    for i, r in enumerate(results[:k]):
        if is_hit(entry, r):
            return i + 1
    return None


def to_pack_input(r):
    header, body = split_header(r["content"])
    return {
        "chunk_id": r["id"],
        "filing_id": r["document_id"],
        "position": r["chunk_index"],
        "header": header,
        "text": body,
        "filing_date": r["filing_date"],
        "rerank_score": r["rerank"],
    }


def metrics_from_ranks(ranks):
    n = len(ranks)
    return {
        "n": n,
        "hit_at_1": sum(1 for rk in ranks if rk == 1) / n,
        "hit_at_5": sum(1 for rk in ranks if rk and rk <= 5) / n,
        "hits_at_5": sum(1 for rk in ranks if rk and rk <= 5),
        "mrr": sum(1 / rk for rk in ranks if rk) / n,
    }


def load_baseline(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    m = data["metrics"]["rerank"]
    return m, data["settings"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden-set", default="eval/golden_set.json")
    ap.add_argument("--baseline", required=True, help="saved run_eval JSON with a rerank run")
    ap.add_argument("--budget", type=int, default=6000)
    ap.add_argument("--label", default="packed")
    args = ap.parse_args()

    base, base_settings = load_baseline(args.baseline)
    if base_settings.get("k") != K or base_settings.get("pool") != POOL:
        raise SystemExit(f"Baseline was run with k={base_settings.get('k')}, pool={base_settings.get('pool')}; "
                         f"this script uses k={K}, pool={POOL}. Refusing to compare.")

    with open(args.golden_set, encoding="utf-8") as f:
        golden = json.load(f)
    entries = [e for e in golden if e.get("type") != "not_found"]

    rows = []
    with SessionLocal() as db:
        for e in entries:
            res = rerank_search(db, e["question"], k=K, ticker=e.get("ticker"), pool=POOL)
            top_n = res[:PACK_TOP_N]
            packed = pack([to_pack_input(r) for r in top_n], args.budget)
            blocks = [{"content": b["text"], "filing_date": b["filing_date"]} for b in packed["blocks"]]
            rows.append({
                "id": e["id"],
                "type": e.get("type"),
                "prod_rank": get_rank(e, res, K),
                "prod_rank_at5": get_rank(e, res, 5),
                "packed_rank": get_rank(e, blocks, K),
                "num_blocks": len(blocks),
                "context_chars": len(packed["context"]),
                "block_chunk_ids": [b["chunk_ids"] for b in packed["blocks"]],
            })

    if not rows:
        raise SystemExit("No scored entries found.")

    prod = metrics_from_ranks([r["prod_rank"] for r in rows])
    packed_m = metrics_from_ranks([r["packed_rank"] for r in rows])
    avg_chars = sum(r["context_chars"] for r in rows) / len(rows)

    print(f"\nScored {len(rows)} questions, budget {args.budget}, avg context {avg_chars:.0f} chars")
    print(f"{'System':<8} | {'Hit@1':<6} | {'Hit@5':<6} | {'MRR':<6}")
    print("-" * 36)
    for name, m in (("BASE", base), ("PROD", prod), ("PACKED", packed_m)):
        print(f"{name:<8} | {m['hit_at_1']:<6.3f} | {m['hit_at_5']:<6.3f} | {m['mrr']:<6.3f}")

    scorer_ok = (
        abs(prod["hit_at_1"] - base["hit_at_1"]) < 1e-6
        and abs(prod["hit_at_5"] - base["hit_at_5"]) < 1e-6
        and abs(prod["mrr"] - base["mrr"]) < 0.0005
    )
    print("\nScorer check: " + (
        "OK, PROD reproduces the baseline rerank run."
        if scorer_ok else
        "FAIL, PROD does not reproduce the baseline. Packed numbers are NOT comparable."
    ))

    keep = scorer_ok and packed_m["hits_at_5"] >= prod["hits_at_5"] and packed_m["mrr"] >= prod["mrr"]
    print("Verdict: " + (
        "KEEP candidate (packed hit@5 and MRR at least as good as prod)."
        if keep else
        "DROP or INVALID (see scorer check and metrics above)."
    ))

    os.makedirs("eval/results", exist_ok=True)
    out_file = f"eval/results/{datetime.now():%Y%m%d_%H%M%S}_{args.label}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "settings": {"k": K, "pool": POOL, "pack_top_n": PACK_TOP_N,
                         "budget": args.budget, "golden_set": args.golden_set,
                         "baseline_file": args.baseline},
            "baseline": base,
            "prod": prod,
            "packed": packed_m,
            "scorer_matches_baseline": scorer_ok,
            "rows": rows,
        }, f, indent=2)
    print(f"Saved {out_file}")


if __name__ == "__main__":
    main()