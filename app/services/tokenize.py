"""Shared stopword-aware tokenizer for BM25 retrieval and context packing.

Pure: no database or model imports. Must behave exactly like the tokenizer
that produced the baseline. scripts/diff_tokenizers.py checks this against git.
"""
import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = {
    "what", "was", "were", "is", "are", "the", "a", "an", "of", "in", "on", "to", "for",
    "and", "or", "does", "do", "did", "how", "which", "who", "s", "its", "it", "by", "with",
}


def tokenize(text: str) -> list[str]:
    toks = _TOKEN_RE.findall(text.lower().replace("\u2019", "'").replace("'s", ""))
    toks = [t[:-1] if len(t) > 3 and t.endswith("s") else t for t in toks]
    return [t for t in toks if t not in _STOP and len(t) > 1]