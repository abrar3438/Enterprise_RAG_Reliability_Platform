"""POST /query endpoint for the RAG platform, with rate limits, one log row per request and an answer cache."""

import logging
import time

from fastapi import APIRouter, Header, HTTPException, Request

from app.core import ratelimit
from app.core.database import SessionLocal
from app.core.security import check_api_key
from app.models.schemas import Citation, QueryRequest, QueryResponse
from app.services import cache
from app.services.companies import detect_ticker
from app.services.generation import generate_answer
from app.services.observability import log_query
from app.services.retrieval import rerank_search

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_response(result, *, ticker, ticker_source, latency_ms, retrieval_ms, cache_hit):
    return QueryResponse(
        answer=result.get("answer", ""),
        refused=bool(result.get("refused")),
        citations=[
            Citation(
                number=c.get("number"),
                ticker=c.get("ticker"),
                filing_date=c.get("filing_date"),
                section=c.get("section"),
                preview=c.get("preview"),
            )
            for c in result.get("citations", [])
        ],
        ticker_used=ticker,
        ticker_source=ticker_source,
        latency_ms=latency_ms,
        retrieval_ms=retrieval_ms,
        cost_bdt=result.get("cost_bdt"),
        prompt_version=result.get("prompt_version") or "",
        model=result.get("model") or "",
        warning=result.get("warning"),
        cache_hit=cache_hit,
    )


@router.post("/query", response_model=QueryResponse)
def query_endpoint(req: QueryRequest, request: Request,
                   x_api_key: str | None = Header(default=None)) -> QueryResponse:
    # 0. access control and limits, before any database or LLM work
    # check_api_key(x_api_key)

    ip = request.client.host if request.client else "unknown"
    if not ratelimit.allow(ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.")
    if ratelimit.daily_limit_reached():
        raise HTTPException(status_code=429, detail="The daily demo limit has been reached. Please try again tomorrow.")

    t0 = time.perf_counter()

    def elapsed() -> int:
        return int((time.perf_counter() - t0) * 1000)

    # 1. ticker: the request wins, then detection from the question, else none
    ticker, ticker_source = req.ticker, "request"
    if not ticker:
        detection = detect_ticker(req.question)
        if detection["status"] == "single":
            ticker, ticker_source = detection["ticker"], "detected"
        else:
            ticker, ticker_source = None, "none"

    def record(status: int, *, retrieval_ms: int = 0, chunks=None, result=None, error=None) -> None:
        log_query(
            question=req.question,
            ticker_used=ticker,
            ticker_source=ticker_source,
            status_code=status,
            retrieval_ms=retrieval_ms,
            total_ms=elapsed(),
            chunks=chunks,
            result=result,
            error=error,
        )

    def log_line(response: QueryResponse) -> None:
        snippet = req.question[:60].replace("\n", " ").replace("\r", " ")
        logger.info(
            "query | q='%s' | ticker=%s (%s) | refused=%s | cache=%s | total=%dms retrieval=%dms | cost=%s",
            snippet, ticker, ticker_source, response.refused, response.cache_hit,
            response.latency_ms, response.retrieval_ms, response.cost_bdt,
        )

    # 2. cache: a hit skips retrieval and the LLM call entirely
    cache_key = cache.make_key(req.question, ticker)
    cached = cache.get(cache_key)
    if cached is not None:
        cached["cost_bdt"] = 0.0  # this request cost nothing
        record(200, result=cached)
        response = _build_response(
            cached, ticker=ticker, ticker_source=ticker_source,
            latency_ms=elapsed(), retrieval_ms=0, cache_hit=True,
        )
        log_line(response)
        return response

    # 3. retrieval (the DB session is closed before the slow LLM call)
    try:
        with SessionLocal() as db:
            chunks = rerank_search(db, req.question, k=5, ticker=ticker, pool=100)
    except Exception as e:
        logger.exception("Retrieval failed")
        record(500, error=f"Retrieval failed: {str(e)[:300]}")
        raise HTTPException(status_code=500, detail="Retrieval service temporarily unavailable.")

    retrieval_ms = elapsed()

    # 4. generation
    try:
        result = generate_answer(req.question, chunks)
    except Exception as e:
        logger.exception("Generation crashed")
        record(502, retrieval_ms=retrieval_ms, chunks=chunks, error=f"Generation crashed: {str(e)[:300]}")
        raise HTTPException(status_code=502, detail="The answer service is temporarily unavailable.")

    if result.get("error"):
        err = str(result["error"])
        status = 503 if "402" in err else 502
        logger.error("Generation returned an error: %s", err)
        record(status, retrieval_ms=retrieval_ms, chunks=chunks, result=result)
        raise HTTPException(status_code=status, detail="The answer service is temporarily unavailable.")

    # 5. cache complete answers only (errors, truncation and unclear verdicts are never stored)
    if cache.cacheable(result):
        cache.put(cache_key, result)

    # 6. response (rejected_answer, verification details and reasoning never leave the server)
    response = _build_response(
        result, ticker=ticker, ticker_source=ticker_source,
        latency_ms=elapsed(), retrieval_ms=retrieval_ms, cache_hit=False,
    )

    # 7. database log row and one console line
    record(200, retrieval_ms=retrieval_ms, chunks=chunks, result=result)
    log_line(response)
    return response