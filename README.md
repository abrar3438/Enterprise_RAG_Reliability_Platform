\# Enterprise RAG Reliability Platform



A production-oriented Retrieval-Augmented Generation platform over SEC EDGAR 10-K filings, built to explore reliable retrieval, grounded citations, and per-query observability.



\*\*Status:\*\* WIP — ingestion pipeline in progress.



\## Stack

\- FastAPI

\- PostgreSQL + pgvector (Docker)

\- SQLAlchemy 2.x, pydantic-settings

\- pytest, httpx



\## Setup



1\. Copy `.env.example` to `.env` and fill in `SEC\_USER\_AGENT` (SEC requires `"Name email"` format).

2\. Start Postgres: `docker compose up -d`

3\. Create venv: `python -m venv venv` → activate: `venv\\Scripts\\activate` → install: `pip install -r requirements.txt`

4\. Initialize the DB schema: `python -m scripts.init\_db`

5\. Download filings: `python -m scripts.download\_edgar`

6\. Run the API: `uvicorn app.main:app --reload` → health check at `/health`



\## Roadmap

\- \[x] FastAPI skeleton + `/health`

\- \[x] Postgres + pgvector via Docker

\- \[x] Schema: `documents`, `chunks` (with HNSW index)

\- \[x] EDGAR downloader

\- \[ ] HTML cleaning + section detection

\- \[ ] Chunking + embeddings

\- \[ ] Hybrid retrieval + reranker

\- \[ ] Query endpoint with citations

\- \[ ] Golden eval set + observability

Enterprise_RAG_Reliability_Platform/
├── .env                              [done]
├── .env.example                      [done]
├── .gitignore                        [done]
├── README.md                         [todo] architecture, setup, eval results, failures, limitations
├── Dockerfile                        [done] CPU torch, models baked in, non-root, healthcheck
├── docker-compose.yml                [done] Postgres + api
├── requirements.txt                  [done]
├── .github/
│   └── workflows/
│       └── ci.yml                    [todo] run pytest on every push
├── app/
│   ├── __init__.py                   [done]
│   ├── main.py                       [done*] serves static page at /
│   ├── core/
│   │   ├── __init__.py               [done]
│   │   ├── config.py                 [edit] add packing_enabled, packing_char_budget, DAILY_QUERY_CAP
│   │   ├── database.py               [done]
│   │   └── ratelimit.py              [todo] per-IP 10/min on /query
│   ├── models/
│   │   ├── __init__.py               [done]
│   │   ├── tables.py                 [done] Document, Chunk, QueryLog
│   │   └── schemas.py                [done*] request/response shapes
│   ├── routers/
│   │   ├── __init__.py               [done]
│   │   ├── query.py                  [done*] POST /query; [todo] history (step 5)
│   │   └── system.py                 [done*] /health, /stats; [todo] /config
│   ├── services/
│   │   ├── __init__.py               [done]
│   │   ├── cleaning.py               [done]
│   │   ├── chunking.py               [done]
│   │   ├── embeddings.py             [done*]
│   │   ├── companies.py              [done*] ticker detection
│   │   ├── filings.py                [done*] fiscal-year filing rule
│   │   ├── tokenize.py               [new] shared tokenizer for BM25 and packing
│   │   ├── retrieval.py              [edit] imports tokenize; adds document_id, chunk_index
│   │   ├── packing.py                [new] context packing (step 1)
│   │   ├── generation.py             [done*] prompt v4, citations, retry, verifier off
│   │   ├── cache.py                  [todo] step 2
│   │   ├── history.py                [todo, last] follow-up rewrite (step 5)
│   │   └── citation_repair.py        [todo, optional] step 7
├── app/static/
│   ├── index.html                    [todo] step 4
│   ├── style.css                     [todo] step 4
│   └── app.js                        [todo] step 4; no innerHTML
├── scripts/
│   ├── __init__.py                   [done]
│   ├── init_db.py                    [done]
│   ├── download_edgar.py             [done]
│   ├── inspect_filing.py             [done]
│   ├── ingest.py                     [done]
│   ├── run_eval.py                   [done] retrieval eval: dense, bm25, hybrid, rerank
│   ├── diff_tokenizers.py            [new] checks tokenizer against git baseline
│   ├── check_overlap.py              [new] counts 150-char overlap matches
│   ├── packed_eval.py                [new] prod vs packed, same scorer
│   └── eval_answers.py               [todo] step 6 answer eval, 3 runs x 20
├── eval/
│   ├── golden_set.json               [done] 20 entries: 16 scored + 4 not_found
│   └── results/                      [done] saved runs; keep the rerank run at MRR 0.503
├── tests/
│   ├── __init__.py                   [todo]
│   ├── test_packing.py               [new] 8 tests
│   ├── test_tokenize.py              [todo]
│   ├── test_chunking.py              [todo]
│   ├── test_cleaning.py              [todo]
│   ├── test_companies.py             [todo]
│   ├── test_filings.py               [todo]
│   ├── test_citations.py             [todo] parser, normalization, preview builder
│   └── test_api.py                   [todo] API key check
├── docs/
│   ├── architecture.png              [todo]
│   └── decisions.md                  [todo]
└── data/                             [done, gitignored]
    ├── manifest.json
    └── raw/<TICKER>/*.htm