"""Run: python -m scripts.inspect_misses"""
import json
import glob
import os

def main():
    # Find the latest baseline file
    files = glob.glob("eval/results/*_baseline.json")
    if not files:
        print("No baseline file found in eval/results/")
        return
        
    latest_file = max(files, key=os.path.getctime)
    print(f"Reading: {latest_file}\n")
    
    with open(latest_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    misses = [
        "tsla-rev-no-year",
        "aapl-rev-fy2025",
        "msft-ni-fy2026",
        "jpm-assets-2025",
        "nvda-concentration",
        "aapl-supply-risk"
    ]
    
    rerank_results = data.get("results", {}).get("rerank", [])
    
    for entry_id in misses:
        entry = next((r for r in rerank_results if r["id"] == entry_id), None)
        if not entry:
            print(f"Entry {entry_id} not found in results.\n")
            continue
            
        print(f"===== MISS: {entry_id} =====")
        for i, chunk in enumerate(entry.get("top_5", [])):
            print(f"  Rank {i+1}: {chunk.get('ticker')} | {chunk.get('filing_date')} | {chunk.get('section')}")
            print(f"  Text: {chunk.get('content')}")
            print()
        print("-" * 60)

if __name__ == "__main__":
    main()