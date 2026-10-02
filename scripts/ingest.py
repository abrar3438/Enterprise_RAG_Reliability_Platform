"""Run: python -m scripts.ingest   (safe to re-run: skips filings already loaded)"""
import json
from datetime import date
from pathlib import Path

from sentence_transformers import SentenceTransformer
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.tables import Chunk, Document
from app.services.chunking import chunk_text
from app.services.cleaning import clean_html, split_sections

model = SentenceTransformer("all-MiniLM-L6-v2")
manifest = json.loads(Path("data/manifest.json").read_text(encoding="utf-8"))

with SessionLocal() as db:
    for f in manifest:
        if db.scalar(select(Document.id).where(Document.source_path == f["source_path"])):
            print(f"skip {f['ticker']} {f['filing_date']} (already ingested)")
            continue

        pieces = []  # (section, text)
        for section, body in split_sections(clean_html(f["source_path"])):
            for c in chunk_text(body):
                pieces.append((section[:200], c.replace("\x00", "")))
        if not pieces:
            print(f"WARN {f['ticker']} {f['filing_date']}: no chunks, skipped")
            continue

        vectors = model.encode(
            [p[1] for p in pieces], batch_size=64, normalize_embeddings=True, show_progress_bar=True
        )

        doc = Document(
            company=f["company"], ticker=f["ticker"], form_type=f["form_type"],
            filing_date=date.fromisoformat(f["filing_date"]), source_path=f["source_path"],
        )
        db.add(doc)
        db.flush()  # assigns doc.id
        db.add_all(
            Chunk(document_id=doc.id, chunk_index=i, section=sec, content=txt, embedding=vec.tolist())
            for i, ((sec, txt), vec) in enumerate(zip(pieces, vectors))
        )
        db.commit()  # one commit per filing
        print(f"ok   {f['ticker']} {f['filing_date']}: {len(pieces)} chunks")