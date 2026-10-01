"""
Two-table design:
  documents  -> one row per source file (e.g. one 10-K filing)
  chunks     -> many rows per document; each holds text + embedding
"""
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# all-MiniLM-L6-v2 produces 384-dim vectors. If you switch embedding
# models later, this number must change (and chunks must be re-embedded).
EMBEDDING_DIM = 384


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    company: Mapped[str] = mapped_column(String(200), index=True)
    ticker: Mapped[str | None] = mapped_column(String(20), index=True)
    form_type: Mapped[str] = mapped_column(String(20), default="10-K")
    filing_date: Mapped[date | None] = mapped_column(Date)
    source_path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # cascade: deleting a document deletes its chunks too
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)  # position within the document
    section: Mapped[str | None] = mapped_column(String(200))  # e.g. "Item 1A. Risk Factors"
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))

    document: Mapped["Document"] = relationship(back_populates="chunks")


# HNSW index = fast approximate nearest-neighbor search over embeddings.
# Cosine distance matches how sentence-transformers embeddings are compared.
Index(
    "ix_chunks_embedding_hnsw",
    Chunk.embedding,
    postgresql_using="hnsw",
    postgresql_with={"m": 16, "ef_construction": 64},
    postgresql_ops={"embedding": "vector_cosine_ops"},
)