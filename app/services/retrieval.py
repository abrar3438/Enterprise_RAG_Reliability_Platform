"""Dense, BM25, hybrid (RRF) and reranked retrieval, with automatic filing selection."""
import re
from functools import lru_cache

from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import Chunk, Document
from app.services.embeddings import get_model
from app.services.filings import resolve_filing_dates

USE_FILING_RULE = True  # set False to reproduce the old behavior


def _dates(query: str, ticker: str | None):
    return resolve_filing_dates(query, ticker) if USE_FILING_RULE else None


# ---------- dense ----------
def dense_search(db: Session, query: str, k: int = 5, ticker: str | None = None) -> list[dict]:
    qvec = get_model().encode(query, normalize_embeddings=True).tolist()
    dist = Chunk.embedding.cosine_distance(qvec)
    stmt = select(Chunk, Document, dist.label("distance")).join(Document, Document.id == Chunk.document_id)
    if ticker:
        stmt = stmt.where(Document.ticker == ticker.upper())
    dates = _dates(query, ticker)
    if dates:
        stmt = stmt.where(Document.filing_date.in_(dates))
    stmt = stmt.order_by(dist).limit(k)
    return [
        {
            "ticker": d.ticker, "filing_date": str(d.filing_date), "section": c.section,
            "distance": round(float(dist_val), 4), "content": c.content,
        }
        for c, d, dist_val in db.execute(stmt)
    ]


# ---------- BM25 ----------
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = {"what", "was", "were", "is", "are", "the", "a", "an", "of", "in", "on", "to", "for",
         "and", "or", "does", "do", "did", "how", "which", "who", "s", "its", "it", "by", "with"}


def tokenize(text: str) -> list[str]:
    toks = _TOKEN_RE.findall(text.lower().replace("\u2019", "'").replace("'s", ""))
    toks = [t[:-1] if len(t) > 3 and t.endswith("s") else t for t in toks]
    return [t for t in toks if t not in _STOP and len(t) > 1]


@lru_cache(maxsize=1)  # builds the index once per process
def _bm25_index():
    from app.core.database import SessionLocal
    with SessionLocal() as db:
        rows = db.execute(
            select(Chunk.id, Chunk.content, Chunk.section, Document.ticker, Document.filing_date)
            .join(Document, Document.id == Chunk.document_id)
        ).all()
    return BM25Okapi([tokenize(r.content) for r in rows]), rows


def bm25_search(query: str, k: int = 5, ticker: str | None = None) -> list[dict]:
    index, rows = _bm25_index()
    scores = index.get_scores(tokenize(query))
    dates = set(_dates(query, ticker) or [])
    ranked = sorted(range(len(rows)), key=lambda i: scores[i], reverse=True)
    out = []
    for i in ranked:
        r = rows[i]
        if ticker and r.ticker != ticker.upper():
            continue
        if dates and r.filing_date not in dates:
            continue
        out.append({"id": r.id, "ticker": r.ticker, "filing_date": str(r.filing_date),
                    "section": r.section, "score": round(float(scores[i]), 3), "content": r.content})
        if len(out) == k:
            break
    return out


# ---------- hybrid (reciprocal rank fusion) ----------
def hybrid_search(db: Session, query: str, k: int = 5, ticker: str | None = None, pool: int = 100) -> list[dict]:
    dense = dense_search(db, query, k=pool, ticker=ticker)
    sparse = bm25_search(query, k=pool, ticker=ticker)
    fused: dict[tuple, dict] = {}
    for results in (dense, sparse):
        for rank, r in enumerate(results):
            key = (r["ticker"], r["filing_date"], r["content"][:120])
            entry = fused.setdefault(key, {**r, "rrf": 0.0})
            entry["rrf"] += 1.0 / (60 + rank + 1)
    return sorted(fused.values(), key=lambda r: r["rrf"], reverse=True)[:k]


# ---------- reranker ----------
@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoder:
    return CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


def rerank_search(db: Session, query: str, k: int = 5, ticker: str | None = None, pool: int = 100) -> list[dict]:
    cands = hybrid_search(db, query, k=pool, ticker=ticker, pool=pool)
    # drop identical text repeated across years, keep the newest filing
    seen, uniq = set(), []
    for r in sorted(cands, key=lambda r: r["filing_date"], reverse=True):
        key = r["content"][:200]
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    scores = get_reranker().predict([(query, r["content"]) for r in uniq])
    for r, s in zip(uniq, scores):
        r["rerank"] = round(float(s), 3)
    return sorted(uniq, key=lambda r: r["rerank"], reverse=True)[:k]