"""Packs reranked chunks into a smaller, less redundant context block.

Pure function: no database, model or network imports.
Neighbour expansion is out of scope for v1 (scope freeze).
"""
import re
from typing import Any

from app.services.tokenize import tokenize

OVERLAP_CHARS = 150
DUP_THRESHOLD = 0.80
SEPARATOR = "\n\n"
_HEADER_RE = re.compile(r"^[^\n]*\([A-Z.\-]+\) 10-K \| [^\n]*\n")


def split_header(content: str | None) -> tuple[str, str]:
    """Return (header, body). The header is the first line when it matches the
    'COMPANY (TICKER) 10-K | Section' format, otherwise ''."""
    content = content or ""
    m = _HEADER_RE.match(content)
    if m:
        return m.group(0)[:-1], content[m.end():]
    return "", content


def _render(block: dict) -> str:
    return f"{block['header']}\n{block['text']}" if block["header"] else block["text"]


def _is_near_duplicate(new_tokens: set, existing_tokens: set) -> bool:
    if not new_tokens:
        return False
    return len(new_tokens & existing_tokens) / len(new_tokens) >= DUP_THRESHOLD


def pack(chunks: list[dict[str, Any]], char_budget: int = 6000) -> dict[str, Any]:
    """chunks: reranked, best first. Each has chunk_id, filing_id, position,
    header, text, filing_date. Returns {"context": str, "blocks": [...]}."""
    if not chunks:
        return {"context": "", "blocks": []}

    rank_of = {c["chunk_id"]: r for r, c in enumerate(chunks)}

    # 1. group by filing; filings ordered by their best-ranked chunk
    filings: dict = {}
    for rank, c in enumerate(chunks):
        fid = c.get("filing_id")
        if fid is None:
            fid = c["chunk_id"]
        entry = filings.setdefault(fid, {"best": rank, "chunks": []})
        entry["chunks"].append(c)
    ordered = sorted(filings.values(), key=lambda f: f["best"])

    # 2-3. within a filing, sort by position; merge consecutive positions
    blocks = []
    for f in ordered:
        fc = sorted(f["chunks"], key=lambda c: c["position"])
        i = 0
        while i < len(fc):
            first = fc[i]
            block = {
                "chunk_ids": [first["chunk_id"]],
                "header": first["header"],
                "text": first["text"],
                "filing_date": str(first.get("filing_date", "")),
                "truncated": False,
            }
            j = i + 1
            while j < len(fc) and fc[j]["position"] == fc[j - 1]["position"] + 1:
                nxt = fc[j]["text"]
                if block["text"][-OVERLAP_CHARS:] == nxt[:OVERLAP_CHARS]:
                    block["text"] += nxt[OVERLAP_CHARS:]   # drop the duplicated overlap
                else:
                    block["text"] += "\n" + nxt
                block["chunk_ids"].append(fc[j]["chunk_id"])
                j += 1
            blocks.append(block)
            i = j

    # 4. order blocks by the best rank of their chunks
    blocks.sort(key=lambda b: min(rank_of[cid] for cid in b["chunk_ids"]))

    # 5. drop near-duplicates: body text only, compared against one kept block at a time
    kept, kept_tokens = [], []
    for b in blocks:
        toks = set(tokenize(b["text"]))
        if any(_is_near_duplicate(toks, kt) for kt in kept_tokens):
            continue
        kept.append(b)
        kept_tokens.append(toks)

    # 6. budget, in rank order; never split a block except the top-1 case
    final = []
    used = 0
    for b in kept:
        if not final:
            if len(_render(b)) > char_budget:
                room = char_budget - len(_render({**b, "text": ""}))
                b["text"] = b["text"][:max(room, 0)]
                b["truncated"] = True
            final.append(b)
            used = len(_render(b))
            continue
        cost = len(_render(b)) + len(SEPARATOR)
        if used + cost > char_budget:
            break
        final.append(b)
        used += cost

    # 7. output
    out = []
    for n, b in enumerate(final, 1):
        out.append({
            "citation_number": n,
            "chunk_ids": b["chunk_ids"],
            "text": _render(b),
            "filing_date": b["filing_date"],
            "truncated": b["truncated"],
        })
    return {"context": SEPARATOR.join(o["text"] for o in out), "blocks": out}