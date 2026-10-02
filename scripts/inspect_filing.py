"""Run: python -m scripts.inspect_filing data/raw/AAPL/<file>.htm"""
import sys

from app.services.cleaning import clean_html, split_sections

text = clean_html(sys.argv[1])
print(f"Clean text: {len(text):,} characters\n")
for name, body in split_sections(text):
    print(f"{len(body):>9,} chars  {name}")
print("\n--- first 600 chars ---\n", text[:600])