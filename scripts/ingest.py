"""Run: python -m scripts.ingest   (safe to re-run: skips filings already loaded)"""
import json
import re
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.tables import Chunk, Document
from app.services.chunking import chunk_text
from app.services.cleaning import clean_html, split_sections
from app.services.embeddings import get_model

def clean_section_label(label: str) -> str:
    if "|" not in label:
        # Collapse repeated spaces and return
        return re.sub(r'\s+', ' ', label).strip()
    
    parts = [p.strip() for p in label.split("|")]
    # drop trailing parts that are only a page number or a page range (e.g. 14 or 9-31)
    while parts:
        last_part = parts[-1]
        if re.match(r'^\d+(-\d+)?$', last_part):
            parts.pop()
        else:
            break
            
    label = " ".join(parts)
    return re.sub(r'\s+', ' ', label).strip()

model = get_model()
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

        # Build contents with headers (no filing date in header)
        contents = []
        for sec, txt in pieces:
            clean_sec = clean_section_label(sec)
            header = f"{f['company']} ({f['ticker']}) {f['form_type']} | {clean_sec}"
            contents.append(f"{header}\n{txt}")

        vectors = model.encode(
            contents, batch_size=64, normalize_embeddings=True, show_progress_bar=True
        )

        doc = Document(
            company=f["company"], ticker=f["ticker"], form_type=f["form_type"],
            filing_date=date.fromisoformat(f["filing_date"]), source_path=f["source_path"],
        )
        db.add(doc)
        db.flush()  # assigns doc.id
        db.add_all(
            Chunk(document_id=doc.id, chunk_index=i, section=sec, content=content_str, embedding=vec.tolist())
            for i, ((sec, _), content_str, vec) in enumerate(zip(pieces, contents, vectors))
        )
        db.commit()  # one commit per filing
        print(f"ok   {f['ticker']} {f['filing_date']}: {len(pieces)} chunks")