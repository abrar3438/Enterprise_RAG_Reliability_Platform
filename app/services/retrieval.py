"""Dense (vector) retrieval over pgvector, with optional ticker filter."""
from functools import lru_cache

from sentence_transformers import SentenceTransformer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import Chunk, Document
from app.services.embeddings import get_model


@lru_cache(maxsize=1)

def dense_search(db: Session, query: str, k: int = 5, ticker: str | None = None) -> list[dict]:
    qvec = get_model().encode(query, normalize_embeddings=True).tolist()
    dist = Chunk.embedding.cosine_distance(qvec)
    stmt = select(Chunk, Document, dist.label("distance")).join(Document, Document.id == Chunk.document_id)
    if ticker:
        stmt = stmt.where(Document.ticker == ticker.upper())
    stmt = stmt.order_by(dist).limit(k)
    return [
        {
            "ticker": d.ticker, "filing_date": str(d.filing_date), "section": c.section,
            "distance": round(float(dist_val), 4), "content": c.content,
        }
        for c, d, dist_val in db.execute(stmt)
    ]