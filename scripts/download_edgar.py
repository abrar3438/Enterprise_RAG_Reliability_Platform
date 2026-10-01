"""
Download the latest 10-K filings for a list of tickers from SEC EDGAR.
Run: python -m scripts.download_edgar
Output: data/raw/<TICKER>/<filing_date>_<accession>.htm + data/manifest.json
"""
import json
import time
from pathlib import Path

import httpx

from app.core.config import settings

TICKERS = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "PFE", "WMT", "TSLA"]
FILINGS_PER_COMPANY = 2
DATA_DIR = Path("data/raw")
MANIFEST = Path("data/manifest.json")

HEADERS = {"User-Agent": settings.sec_user_agent}


def get(client: httpx.Client, url: str) -> httpx.Response:
    time.sleep(0.2)  # stay well under SEC's 10 requests/second limit
    resp = client.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return resp


def main():
    if not settings.sec_user_agent:
        raise SystemExit("Set SEC_USER_AGENT in .env (e.g. 'Your Name you@email.com')")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []

    with httpx.Client() as client:
        # ticker -> CIK (SEC's company ID) lookup table
        tickers_json = get(client, "https://www.sec.gov/files/company_tickers.json").json()
        cik_by_ticker = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in tickers_json.values()}

        for ticker in TICKERS:
            cik = cik_by_ticker.get(ticker)
            if not cik:
                print(f"! {ticker}: CIK not found, skipping")
                continue

            sub = get(client, f"https://data.sec.gov/submissions/CIK{cik}.json").json()
            recent = sub["filings"]["recent"]
            company = sub["name"]

            saved = 0
            for i, form in enumerate(recent["form"]):
                if form != "10-K" or saved >= FILINGS_PER_COMPANY:
                    continue
                accession = recent["accessionNumber"][i]
                filing_date = recent["filingDate"][i]
                primary_doc = recent["primaryDocument"][i]

                url = (
                    f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                    f"{accession.replace('-', '')}/{primary_doc}"
                )
                out_dir = DATA_DIR / ticker
                out_dir.mkdir(exist_ok=True)
                out_path = out_dir / f"{filing_date}_{accession}.htm"

                if not out_path.exists():
                    out_path.write_bytes(get(client, url).content)
                print(f"+ {ticker} {filing_date} -> {out_path}")

                manifest.append({
                    "company": company,
                    "ticker": ticker,
                    "form_type": form,
                    "filing_date": filing_date,
                    "source_path": str(out_path),
                    "source_url": url,
                })
                saved += 1

    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print(f"\nDone. {len(manifest)} filings listed in {MANIFEST}")


if __name__ == "__main__":
    main()