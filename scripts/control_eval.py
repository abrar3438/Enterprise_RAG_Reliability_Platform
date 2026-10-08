"""Run: python -m scripts.control_eval --baseline eval/results/20261008_211316_recheck.json --packed eval/results/20261008_213510_packed_top10_fixed.json --budget 6000

Control for packed_eval: the same top-10 candidates, NO packing. Whole chunks are
added in rank order until the character budget is full (top-1 always included).
If this matches PACKED, the gain comes from the larger candidate pool, not packing."""
import argparse
import json
import os
from datetime import datetime

from app.core.database import SessionLocal
from app.services.retrieval import rerank_search
from scripts.packed_eval import K, POOL, PACK_TOP_N, get_rank, load_baseline, metrics_from_ranks


def take_within_budget(res, budget):
    kept, used = [], 0
    for r in res:
        cost = len(r["content"]) + (2 if kept else 0)
        if kept and used + cost > budget:
            break
        kept.append(r)
        used += cost
    return kept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden-set", default="eval/golden_set.json")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--packed", required=True, help="saved packed_eval run to compare against")
    ap.add_argument("--budget", type=int, default=6000)
    ap.add_argument("--label", default="control")
    args = ap.parse_args()

    base, _ = load_baseline(args.baseline)
    with open(args.packed, encoding="utf-8") as f:
        packed_rows = {r["id"]: r for r in json.load(f)["rows"]}

    with open(args.golden_set, encoding="utf-8") as f:
        entries = [e for e in json.load(f) if e.get("type") != "not_found"]

    rows = []
    with SessionLocal() as db:
        for e in entries:
            res = rerank_search(db, e["question"], k=K, ticker=e.get("ticker"), pool=POOL)
            kept = take_within_budget(res[:PACK_TOP_N], args.budget)
            pk = packed_rows.get(e["id"])
            if pk is None:
                raise SystemExit(f"Question {e['id']} missing from the packed run file.")
            rows.append({
                "id": e["id"],
                "type": e.get("type"),
                "prod_rank": get_rank(e, res, K),
                "prod_rank_at5": get_rank(e, res, 5),
                "control_rank": get_rank(e, kept, K),
                "control_chunks": len(kept),
                "control_chars": sum(len(r["content"]) for r in kept) + 2 * max(len(kept) - 1, 0),
                "packed_rank": pk["packed_rank"],
            })

    prod10 = metrics_from_ranks([r["prod_rank"] for r in rows])
    prod5 = metrics_from_ranks([r["prod_rank_at5"] for r in rows])
    control = metrics_from_ranks([r["control_rank"] for r in rows])
    packed = metrics_from_ranks([r["packed_rank"] for r in rows])
    n = len(rows)
    avg_chunks = sum(r["control_chunks"] for r in rows) / n
    avg_chars = sum(r["control_chars"] for r in rows) / n

    print(f"\nScored {n} questions, budget {args.budget}")
    print(f"Control: avg {avg_chunks:.1f} whole chunks, {avg_chars:.0f} chars")
    print(f"{'System':<10} | {'Hit@1':<6} | {'Hit@5':<6} | {'MRR':<6}")
    print("-" * 40)
    for name, m in (("BASE", base), ("PROD@10", prod10), ("PROD@5", prod5),
                    ("CONTROL", control), ("PACKED", packed)):
        print(f"{name:<10} | {m['hit_at_1']:<6.3f} | {m['hit_at_5']:<6.3f} | {m['mrr']:<6.3f}")

    scorer_ok = abs(prod10["mrr"] - base["mrr"]) < 0.0005 and abs(prod10["hit_at_5"] - base["hit_at_5"]) < 1e-6
    print("\nScorer check: " + ("OK" if scorer_ok else "FAIL, comparison invalid"))

    gap_h5 = packed["hits_at_5"] - control["hits_at_5"]
    gap_mrr = packed["mrr"] - control["mrr"]
    if not scorer_ok:
        verdict = "INVALID (scorer check failed)"
    elif gap_h5 > 0 and gap_mrr > 0:
        verdict = "PACKING ADDS VALUE over the unpacked control on this set (directional, n=16)"
    elif gap_h5 == 0 and abs(gap_mrr) < 0.005:
        verdict = "NO DIFFERENCE: gain comes from the larger candidate pool, not packing"
    else:
        verdict = "UNCLEAR or PACKING WORSE than control; do not keep on retrieval alone"
    print(f"Packed vs control: hit@5 {gap_h5:+d}, MRR {gap_mrr:+.3f}")
    print(f"Verdict: {verdict}")

    os.makedirs("eval/results", exist_ok=True)
    out = f"eval/results/{datetime.now():%Y%m%d_%H%M%S}_{args.label}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"settings": {"budget": args.budget, "baseline_file": args.baseline,
                                "packed_file": args.packed},
                   "prod10": prod10, "prod5": prod5, "control": control, "packed": packed,
                   "rows": rows}, f, indent=2)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()