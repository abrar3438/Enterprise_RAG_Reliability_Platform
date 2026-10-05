"""Run: python -m scripts.test_verifier
Does the verifier catch the wrong JPM answer (VIE total) and accept the right one?"""
from app.core.database import SessionLocal
from app.services.generation import _verify
from app.services.retrieval import rerank_search

QUESTION = "What were JPMorgan Chase's consolidated total assets at the end of 2025?"
RUNS = 3


def pick(numbered, number_text, fallback_index):
    """Find the retrieved chunk containing a number; fall back to a fixed position if none does."""
    for n, c in numbered:
        if number_text in (c.get("content") or ""):
            return n, c
    print(f"NOTE: no retrieved chunk contains {number_text}; falling back to chunk {fallback_index}")
    return numbered[fallback_index - 1] if len(numbered) >= fallback_index else numbered[0]


def run_case(answer, cited):
    verdicts, cost = [], 0.0
    for _ in range(RUNS):
        v = _verify(QUESTION, answer, cited)
        verdicts.append(v["verdict"] or f"NONE({v['error']})")
        cost += v["cost"] or 0.0
    return verdicts, cost


def main() -> None:
    with SessionLocal() as db:
        chunks = rerank_search(db, QUESTION, k=5, ticker="JPM", pool=100)
    numbered = list(enumerate(chunks, 1))

    wrong_n, wrong_chunk = pick(numbered, "43,295", 4)
    right_n, right_chunk = pick(numbered, "4,424,900", 2)
    print(f"Wrong figure found in chunk [{wrong_n}], right figure in chunk [{right_n}]")

    wrong = ("JPMorgan Chase & Co. 10-K filed 2026-02-13 reports consolidated Total assets of "
             f"$ 43,295 million at December 31, 2025 [{wrong_n}]")
    right = ("JPMorgan Chase & Co. 10-K filed 2026-02-13 reports consolidated total assets of "
             f"$4,424,900 million at December 31, 2025 (Total liabilities and stockholders' equity) [{right_n}]")

    cases = [
        ("WRONG answer, cited chunk only", wrong, [(wrong_n, wrong_chunk)], "UNSUPPORTED"),
        ("WRONG answer, all 5 chunks", wrong, numbered, "UNSUPPORTED"),
        ("RIGHT answer, cited chunk only", right, [(right_n, right_chunk)], "SUPPORTED"),
        ("RIGHT answer, all 5 chunks", right, numbered, "SUPPORTED"),
    ]

    total_cost, good = 0.0, {}
    print()
    for label, answer, cited, expected in cases:
        verdicts, cost = run_case(answer, cited)
        total_cost += cost
        good[label] = verdicts.count(expected) == RUNS
        print(f"{label:34} -> {verdicts}  (expected {expected} x{RUNS})")

    print(f"\nTotal verifier cost: {total_cost:.4f} BDT")
    if good["WRONG answer, all 5 chunks"] and good["RIGHT answer, all 5 chunks"]:
        print("DECISION: verifier works with ALL chunks -> set VERIFY_WITH_ALL_CHUNKS = True in generation.py")
    elif good["WRONG answer, cited chunk only"] and good["RIGHT answer, cited chunk only"]:
        print("DECISION: verifier works with the cited chunk only -> keep the current setting")
    else:
        print("DECISION: verifier is unreliable here -> set verify_answers default to False in config.py")


if __name__ == "__main__":
    main()