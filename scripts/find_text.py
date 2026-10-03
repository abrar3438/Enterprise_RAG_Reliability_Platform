"""Run: python -m scripts.find_text <TICKER> "<phrase>" [FILING_DATE]"""
import sys
from datetime import date
from sqlalchemy import select, func
from app.core.database import SessionLocal
from app.models.tables import Chunk, Document

def main(ticker: str, phrase: str, filing_date_str: str | None = None):
    filing_date = date.fromisoformat(filing_date_str) if filing_date_str else None
    
    with SessionLocal() as db:
        base_stmt = select(
            Document.filing_date, 
            Chunk.section, 
            Chunk.content, 
            func.strpos(func.lower(Chunk.content), phrase.lower()).label("pos")
        ).join(Document, Document.id == Chunk.document_id)\
         .where(Document.ticker == ticker.upper())\
         .where(func.strpos(func.lower(Chunk.content), phrase.lower()) > 0)

        if filing_date:
            base_stmt = base_stmt.where(Document.filing_date == filing_date)

        # Get total count from a subquery
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_count = db.execute(count_stmt).scalar_one()

        if total_count == 0:
            print("no matches")
            return

        stmt = base_stmt.order_by(Document.filing_date.desc(), Chunk.chunk_index).limit(10)
        results = db.execute(stmt).all()

        for f_date, section, content, pos in results:
            pos = int(pos) - 1  # strpos is 1-indexed
            start = max(0, pos - 150)
            end = min(len(content), pos + len(phrase) + 150)
            # Print original-case text, replacing newlines with spaces
            snippet = content[start:end].replace(chr(10), " ")
            
            print(f"\n===== {f_date} | {section} =====")
            print(snippet)

        print(f"\nTotal matches: {total_count}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m scripts.find_text <TICKER> \"<phrase>\" [FILING_DATE]")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)