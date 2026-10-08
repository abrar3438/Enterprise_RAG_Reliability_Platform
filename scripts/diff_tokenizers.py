"""Run: python -m scripts.diff_tokenizers [--with-corpus] [--rev 267c284]
Compares app/services/tokenize.py against the tokenizer committed in git.
Exit code 0 only when every input tokenizes identically."""
import argparse
import ast
import json
import re
import subprocess
import sys

from app.services.tokenize import tokenize as new_tokenize


def load_committed_tokenizer(rev: str):
    src = subprocess.run(
        ["git", "show", f"{rev}:app/services/retrieval.py"],
        capture_output=True, text=True, check=True,
    ).stdout
    tree = ast.parse(src)
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in ("_TOKEN_RE", "_STOP") for t in node.targets
        ):
            nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == "tokenize":
            nodes.append(node)
    if len(nodes) != 3:
        raise RuntimeError(f"Expected _TOKEN_RE, _STOP and tokenize in {rev}, found {len(nodes)} nodes")
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {"re": re}
    exec(compile(module, f"<{rev}:retrieval.py>", "exec"), ns)
    return ns["tokenize"]


def sample_corpus_texts(n: int = 500) -> list[str]:
    from sqlalchemy import func, select
    from app.core.database import SessionLocal
    from app.models.tables import Chunk
    with SessionLocal() as db:
        rows = db.execute(select(Chunk.content).order_by(func.random()).limit(n)).scalars().all()
    return [r or "" for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="267c284")
    ap.add_argument("--with-corpus", action="store_true")
    ap.add_argument("--golden-set", default="eval/golden_set.json")
    args = ap.parse_args()

    old_tokenize = load_committed_tokenizer(args.rev)

    with open(args.golden_set, encoding="utf-8") as f:
        inputs = [e["question"] for e in json.load(f)]
    if args.with_corpus:
        inputs += sample_corpus_texts()

    mismatches = []
    for text in inputs:
        old, new = old_tokenize(text), new_tokenize(text)
        if old != new:
            mismatches.append((text, old, new))

    print(f"Baseline rev: {args.rev}")
    print(f"Compared {len(inputs)} inputs, {len(mismatches)} mismatches.")
    for text, old, new in mismatches[:10]:
        print(f"MISMATCH: {text[:80]!r}")
        print(f"  committed: {old[:20]}")
        print(f"  new:       {new[:20]}")
    if mismatches:
        print("FAIL: tokenizer output differs. Do not evaluate packing or trust BM25 baseline.")
        return 1
    print("SUCCESS: tokenizer output is identical to the committed baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())