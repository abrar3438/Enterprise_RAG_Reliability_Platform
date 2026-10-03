"""Run: python -m scripts.verify_eval"""
import json
from datetime import date
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.tables import Chunk, Document

def main():
    with open("eval/golden_set.json", "r", encoding="utf-8") as f:
        golden_set = json.load(f)
        
    ok_count = 0
    broken_count = 0
    skip_count = 0
    
    with SessionLocal() as db:
        for entry in golden_set:
            entry_id = entry.get('id', 'UNKNOWN_ID')
            
            if entry.get("type") == "not_found":
                print(f"[SKIP] {entry_id}")
                skip_count += 1
                continue

            ticker = entry.get("ticker")
            filing_date_str = entry.get("filing_date")
            filing_date = date.fromisoformat(filing_date_str) if filing_date_str else None
            
            snippets = entry.get("evidence_snippet", [])
            if isinstance(snippets, str):
                snippets = [snippets]
                
            stmt = select(Chunk.content, Document.filing_date)\
                .join(Document, Document.id == Chunk.document_id)
                
            if ticker:
                stmt = stmt.where(Document.ticker == ticker.upper())
            if filing_date:
                stmt = stmt.where(Document.filing_date == filing_date)
                
            results = db.execute(stmt).all()
            
            total_matches = 0
            matched_dates = set()
            snippet_counts = []
            
            for snippet in snippets:
                count = 0
                for content, f_date in results:
                    if snippet in content:
                        count += 1
                        matched_dates.add(str(f_date))
                snippet_counts.append(f"'{snippet}': {count}")
                total_matches += count
                
            if total_matches > 0:
                status = "OK"
                ok_count += 1
            else:
                status = "BROKEN"
                broken_count += 1
                
            print(f"[{status}] {entry_id} | Total: {total_matches} | Dates: {list(matched_dates)}")
            for sc in snippet_counts:
                print(f"  -> {sc}")

    print(f"\nSummary: {ok_count} OK, {broken_count} BROKEN, {skip_count} SKIP")

if __name__ == "__main__":
    main()