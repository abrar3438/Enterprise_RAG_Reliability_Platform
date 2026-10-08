"""One log row per /query request. Logging must never break a request."""
import logging

from app.core.database import SessionLocal
from app.models.tables import QueryLog

logger = logging.getLogger(__name__)


def _chunk_summary(chunks) -> list[dict]:
    return [
        {
            "id": c.get("id"),
            "ticker": c.get("ticker"),
            "filing_date": str(c.get("filing_date")),
            "rerank": c.get("rerank"),
        }
        for c in (chunks or [])
    ]


def log_query(
    *,
    question: str,
    ticker_used: str | None,
    ticker_source: str,
    status_code: int,
    retrieval_ms: int,
    total_ms: int,
    chunks=None,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    """Store the request, the retrieved chunk ids with rerank scores, the answer and the cost.
    Never stores headers or the API key. Any failure is logged as a warning and swallowed."""
    result = result or {}
    try:
        err = error or result.get("error")
        row = QueryLog(
            question=(question or "")[:2000],
            ticker_used=ticker_used,
            ticker_source=ticker_source,
            status_code=status_code,
            refused=result.get("refused"),
            answer=result.get("answer") or None,
            rejected_answer=result.get("rejected_answer"),
            verification=result.get("verification"),
            citations=result.get("citations") or [],
            chunks=_chunk_summary(chunks),
            prompt_version=result.get("prompt_version"),
            model=result.get("model"),
            prompt_tokens=result.get("prompt_tokens"),
            completion_tokens=result.get("completion_tokens"),
            finish_reason=result.get("finish_reason"),
            retrieval_ms=retrieval_ms,
            total_ms=total_ms,
            cost_bdt=result.get("cost_bdt"),
            error=str(err)[:500] if err else None,
        )
        with SessionLocal() as db:
            db.add(row)
            db.commit()
    except Exception:
        logger.warning("Could not write query log", exc_info=True)