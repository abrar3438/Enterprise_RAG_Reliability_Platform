"""Run: python -m scripts.check_overlap
Counts adjacent chunk pairs (same document, consecutive chunk_index) whose body
text shares the 150-char overlap. Uses the same header split as packing.py."""
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.tables import Chunk
from app.services.packing import split_header

OVERLAP = 150


def main() -> None:
    with SessionLocal() as db:
        rows = db.execute(
            select(Chunk.id, Chunk.document_id, Chunk.chunk_index, Chunk.content)
            .order_by(Chunk.document_id, Chunk.chunk_index)
        ).all()

    with_header = 0
    bodies = {}
    for r in rows:
        header, body = split_header(r.content)
        with_header += bool(header)
        bodies[r.id] = body

    adjacent = matches = 0
    for prev, curr in zip(rows, rows[1:]):
        if prev.document_id != curr.document_id or curr.chunk_index != prev.chunk_index + 1:
            continue
        adjacent += 1
        if bodies[prev.id][-OVERLAP:] == bodies[curr.id][:OVERLAP]:
            matches += 1

    print(f"Chunks total: {len(rows)}")
    print(f"Chunks with header line: {with_header}")
    print(f"Adjacent pairs: {adjacent}")
    print(f"Pairs matching {OVERLAP}-char body overlap: {matches}")
    if adjacent:
        print(f"Match rate: {matches / adjacent * 100:.2f}%")


if __name__ == "__main__":
    main()