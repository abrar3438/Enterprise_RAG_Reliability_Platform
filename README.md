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

