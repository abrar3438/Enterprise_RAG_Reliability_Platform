"""Run clean_html + split_sections on every filing in the manifest.

Run: python -m scripts.inspect_all
"""
import json
from pathlib import Path

from app.services.cleaning import clean_html, split_sections

KEY_ITEMS = {"1", "1A", "7", "8"}
MIN_CHARS = 500


def item_key(name: str) -> str:
    return name.split(" ")[1].rstrip(".")


def main() -> None:
    manifest = json.loads(Path("data/manifest.json").read_text())
    if isinstance(manifest, dict):  # in case it's {"filings": [...]}
        manifest = next(iter(manifest.values()))
    print(f"Manifest entries: {len(manifest)}\n")

    problems = []
    for entry in manifest:
        ticker = entry.get("ticker", "?")
        raw = entry.get("path") or entry.get("file") or entry.get("source_path")
        label = f"{ticker} {Path(raw).name[:10] if raw else '?'}"
        try:
            sections = split_sections(clean_html(raw))
            sizes = {item_key(n): len(b) for n, b in sections}
            missing = sorted(KEY_ITEMS - sizes.keys())
            thin = sorted(k for k in KEY_ITEMS & sizes.keys() if sizes[k] < MIN_CHARS)
            status = "OK" if not (missing or thin) else "CHECK"
            print(f"{label:<18} {len(sections):>3} sections  "
                  + "  ".join(f"{k}:{sizes.get(k, 0):,}" for k in sorted(KEY_ITEMS))
                  + f"  {status}")
            if status == "CHECK":
                problems.append((label, f"missing={missing} thin={thin}"))
        except Exception as e:
            print(f"{label:<18} ERROR: {e}")
            problems.append((label, str(e)))

    print(f"\n{len(manifest)} filings, {len(problems)} flagged")
    for label, why in problems:
        print(f"  {label}: {why}")


if __name__ == "__main__":
    main()