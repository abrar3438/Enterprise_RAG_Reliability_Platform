"""
Turn a raw 10-K .htm file into clean text, then split it by "Item" sections.
"""
import warnings
from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
import re
from pathlib import Path

from bs4 import BeautifulSoup

ITEM_RE = re.compile(r"^\s*item\s+(\d{1,2}[ABC]?)\s*[\.\:\-–—]?\s*(.*)$", re.IGNORECASE)


def clean_html(path: str | Path) -> str:
    html = Path(path).read_bytes()
    soup = BeautifulSoup(html, "lxml")

    # hidden XBRL metadata, scripts, styles: not real content
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    for tag in soup.find_all(lambda t: t.name and t.name.lower() == "ix:header"):
        tag.decompose()

    # tables -> one text line per row, cells joined with " | "
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c]
            if cells:
                rows.append(" | ".join(cells))
        table.replace_with(soup.new_string("\n" + "\n".join(rows) + "\n"))

    text = soup.get_text("\n")
    text = text.replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    return re.sub(r"\n{3,}", "\n\n", text)


def split_sections(text: str) -> list[tuple[str, str]]:
    """Return [(section_name, section_text)]. Keeps the longest span per Item,
    so the short table-of-contents entries lose to the real sections."""
    lines = text.split("\n")
    heads = []  # (line_index, item_key, title)
    for i, ln in enumerate(lines):
        m = ITEM_RE.match(ln)
        if m and len(ln) < 200:
            heads.append((i, m.group(1).upper(), m.group(2).strip()))

    best: dict[str, tuple[int, str, str]] = {}
    for n, (i, key, title) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        body = "\n".join(lines[i + 1 : end])
        if key not in best or len(body) > len(best[key][2]):
            best[key] = (i, title, body)

    ordered = sorted(best.items(), key=lambda kv: kv[1][0])
    result = [(f"Item {k}. {title}".strip(". "), body) for k, (_, title, body) in ordered]

    if not heads:
        return [("Unsectioned", text)]
    preamble = "\n".join(lines[: heads[0][0]])
    if preamble.strip():
        result.insert(0, ("Unsectioned", preamble))
    return result