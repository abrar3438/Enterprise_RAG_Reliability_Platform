"""Split section text into overlapping chunks, breaking on line boundaries."""

CHUNK_CHARS = 800    # all-MiniLM-L6-v2 truncates at 256 tokens (~1000 chars)
OVERLAP_CHARS = 150


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    chunks, current, fresh = [], "", False  # fresh = current has new text beyond the overlap tail
    for line in text.split("\n"):
        while len(line) > size:  # very long line: hard split
            if fresh:
                chunks.append(current)
            chunks.append(line[:size])
            current, fresh = "", False
            line = line[size - overlap :]
        if fresh and len(current) + len(line) + 1 > size:
            chunks.append(current)
            current, fresh = current[-overlap:], False
        current = f"{current}\n{line}" if current else line
        fresh = True
    if fresh:
        chunks.append(current)
    return [c.strip() for c in chunks if len(c.strip()) > 40]