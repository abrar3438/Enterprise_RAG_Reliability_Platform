"""Run: python -m scripts.try_answer                              (10 built-in questions)
   or:  python -m scripts.try_answer "question" [TICKER] [--runs N]"""
import argparse
import json
import os
from collections import Counter
from datetime import datetime

from app.core.database import SessionLocal
from app.services.generation import generate_answer, normalize_answer
from app.services.retrieval import rerank_search


def norm(text: str) -> str:
    return normalize_answer(text).lower().replace("\u2019", "'").replace("\u2018", "'")


TESTS = [
    {"q": "What was Tesla's total revenue in 2025?", "ticker": "TSLA", "type": "answerable",
     "any": ["94.83", "94,827", "94.8 billion"]},
    {"q": "What was Microsoft's net income in fiscal 2026?", "ticker": "MSFT", "type": "faithfulness",
     "any": ["133.7", "133,749"]},
    {"q": "How much did the jury award in the Autopilot accident trial?", "ticker": "TSLA", "type": "answerable",
     "any": ["129"]},
    {"q": "What are Walmart's reportable segments?", "ticker": "WMT", "type": "answerable",
     "all": ["walmart u.s.", "international", "sam's club"]},
    {"q": "What was Apple's total revenue in fiscal 2025?", "ticker": "AAPL", "type": "faithfulness",
     "any": ["416,161", "416.2"]},
    {"q": "What were JPMorgan Chase's consolidated total assets at the end of 2025?", "ticker": "JPM",
     "type": "faithfulness", "any": ["4,424,900", "4.42"]},
    {"q": "What was Tesla's revenue from Cybertruck in 2025?", "ticker": "TSLA", "type": "not_found"},
    {"q": "What is Nvidia's market share in AI chips?", "ticker": "NVDA", "type": "not_found"},
    {"q": "How many Vision Pro headsets did Apple sell in fiscal 2025?", "ticker": "AAPL", "type": "not_found"},
    {"q": "What was ExxonMobil's total revenue in 2024?", "ticker": None, "type": "not_found"},
]


def passes(test: dict, r: dict) -> tuple[bool, str]:
    if r.get("error"):
        return False, f"Error: {r['error']}"
    if test["type"] == "not_found":
        return (True, "") if r.get("refused") else (False, "Did not return the refusal sentence")
    if test["type"] == "faithfulness":  # known retrieval misses: refuse, or state the correct figure
        if r.get("refused"):
            return True, ""
        a = norm(r.get("answer", ""))
        if any(n in a for n in test["any"]):
            return True, ""
        return False, "Stated a figure that is not the known correct one (confident wrong answer)"
    if r.get("refused"):
        return False, "Model refused (answer probably not in the retrieved chunks)"
    if not r.get("citations"):
        return False, "No citations parsed from the answer"
    a = norm(r.get("answer", ""))
    if "any" in test and not any(n in a for n in test["any"]):
        return False, f"None of {test['any']} found in the answer"
    if "all" in test and not all(n in a for n in test["all"]):
        return False, f"Not all of {test['all']} found in the answer"
    return True, ""


def print_chunks(chunks: list[dict]) -> None:
    print("  Retrieved chunks:")
    for i, c in enumerate(chunks, 1):
        text = (c.get("content") or "")[:200].replace("\n", " ")
        print(f"   [{i}] {c.get('ticker')} | {c.get('filing_date')} | {(c.get('section') or '')[:40]}")
        print(f"       {text}")


def run_test(test: dict, db, show_chunks: bool = False):
    q, ticker = test["q"], test["ticker"]
    chunks = rerank_search(db, q, k=5, ticker=ticker, pool=100)
    result = generate_answer(q, chunks)

    print(f"\n{'=' * 60}")
    print(f"Question: {q} (Ticker: {ticker or 'None'})")
    if test["type"] == "faithfulness":
        print("Label: known retrieval miss (pass = refuse or correct figure)")
    print(f"Answer: {result.get('answer', '')}")
    print(f"Refused: {result.get('refused', False)}")
    for cite in result.get("citations", []):
        print(f"  Citation [{cite.get('number')}]: {cite.get('ticker')} | {cite.get('filing_date')} | {cite.get('section')}")
    print(f"Verification: {result.get('verification')}"
          + (f" (error: {result['verification_error']})" if result.get("verification_error") else ""))
    if result.get("rejected_answer"):
        print(f"Rejected answer (log only): {result['rejected_answer']}")
    print(f"Finish Reason: {result.get('finish_reason')} | Attempts: {result.get('attempts')} | "
          f"Latency (ms): {result.get('latency_ms')}")
    print(f"Cost (BDT): {result.get('cost_bdt')} | Balance After: {result.get('balance_after')} | "
          f"Prompt: {result.get('prompt_version')}")
    if result.get("error"):
        print(f"Error: {result['error']}")
    if result.get("warning"):
        print(f"Warning: {result['warning']}")

    ok = None
    if test["type"] != "custom":
        ok, reason = passes(test, result)
        print(f"Status: {'PASS' if ok else 'FAIL'}")
        if not ok:
            print(f"  FAIL Reason: {reason}")
    if show_chunks or ok is False or test["type"] == "faithfulness":
        print_chunks(chunks)

    preview = [{"ticker": c.get("ticker"), "filing_date": str(c.get("filing_date")),
                "section": c.get("section"), "text": (c.get("content") or "")[:200]} for c in chunks]
    return ok, result, preview


def run_suite() -> None:
    os.makedirs("eval/results", exist_ok=True)
    output_file = f"eval/results/answers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    log, lines = [], {"answerable": [], "faithfulness": [], "not_found": []}
    passed = {"answerable": 0, "faithfulness": 0, "not_found": 0}
    total = {"answerable": 0, "faithfulness": 0, "not_found": 0}
    stop_count = 0
    total_cost = 0.0
    verification_counts = Counter()

    with SessionLocal() as db:
        for test in TESTS:
            ok, result, preview = run_test(test, db)
            log.append({"question": test["q"], "type": test["type"], "passed": ok,
                        "result": result, "chunks": preview})
            total[test["type"]] += 1
            if ok:
                passed[test["type"]] += 1
            lines[test["type"]].append(f"{'PASS' if ok else 'FAIL'} | {test['q']}")
            if result.get("finish_reason") == "stop":
                stop_count += 1
            if isinstance(result.get("cost_bdt"), (int, float)):
                total_cost += result["cost_bdt"]
            verification_counts[result.get("verification")] += 1
            with open(output_file, "w", encoding="utf-8") as f:  # save after every question
                json.dump({"results": log}, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}\n===== PASS/FAIL SUMMARY =====")
    for title, key in (("Answerable", "answerable"),
                       ("Faithfulness (known retrieval misses: refuse or correct figure)", "faithfulness"),
                       ("Not found", "not_found")):
        print(f"\n-- {title} --")
        print("\n".join(lines[key]))
    print("\n===== FINAL TOTALS =====")
    print(f"Answerable passed: {passed['answerable']}/{total['answerable']}")
    print(f"Faithfulness passed: {passed['faithfulness']}/{total['faithfulness']}")
    print(f"Not-found refused: {passed['not_found']}/{total['not_found']}")
    print(f"Calls ended with 'stop': {stop_count}/{len(TESTS)}")
    print(f"Verification: {dict(verification_counts)}")
    print(f"Total cost (BDT): {total_cost:.4f}")
    print(f"Results saved to {output_file}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="?")
    parser.add_argument("ticker", nargs="?")
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()

    if not args.question:
        run_suite()
        return

    results = []
    with SessionLocal() as db:
        for i in range(args.runs):
            if args.runs > 1:
                print(f"\n##### RUN {i + 1}/{args.runs} #####")
            _, result, _ = run_test({"q": args.question, "ticker": args.ticker, "type": "custom"},
                                    db, show_chunks=(i == 0))
            results.append(result)
    if args.runs > 1:
        print("\n===== RUN SUMMARY =====")
        for i, r in enumerate(results, 1):
            print(f"{i}. refused={r.get('refused')} verification={r.get('verification')} | "
                  f"{(r.get('answer') or '')[:140]}")


if __name__ == "__main__":
    main()