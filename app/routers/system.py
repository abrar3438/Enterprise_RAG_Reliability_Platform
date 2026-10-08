"""Health and stats endpoints. /health is open. /stats requires the API key when API_KEY is set."""
from fastapi import APIRouter, Header
from sqlalchemy import func, select, text

from app.core.database import SessionLocal
from app.core.security import check_api_key
from app.models.tables import QueryLog
from app.services import cache

router = APIRouter()


@router.get("/health")
def health():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok}


@router.get("/stats")
def stats(x_api_key: str | None = Header(default=None)):
    check_api_key(x_api_key)

    with SessionLocal() as db:
        totals = db.execute(select(
            func.count(QueryLog.id),
            func.count().filter(QueryLog.status_code == 200),
            func.count().filter(QueryLog.status_code >= 500),
            func.count().filter(QueryLog.refused.is_(True)),
            func.coalesce(func.sum(QueryLog.cost_bdt), 0.0),
            func.avg(QueryLog.total_ms),
            func.avg(QueryLog.retrieval_ms),
            func.percentile_cont(0.5).within_group(QueryLog.total_ms),
            func.percentile_cont(0.95).within_group(QueryLog.total_ms),
        )).one()

        recent_errors = db.execute(
            select(QueryLog.created_at, QueryLog.status_code, QueryLog.error)
            .where(QueryLog.error.is_not(None))
            .order_by(QueryLog.id.desc())
            .limit(5)
        ).all()

    (total, ok, server_errors, refused, cost, avg_total, avg_retrieval, p50, p95) = totals

    return {
        "requests": {
            "total": total,
            "ok_200": ok,
            "server_errors_5xx": server_errors,
            "refused": refused,
        },
        "cost_bdt_total": round(float(cost), 4),
        "cost_bdt_per_request": round(float(cost) / total, 4) if total else 0.0,
        "latency_ms": {
            "avg_total": round(avg_total or 0),
            "avg_retrieval": round(avg_retrieval or 0),
            "p50_total": round(p50 or 0),
            "p95_total": round(p95 or 0),
        },
        "recent_errors": [
            {
                "at": row.created_at.isoformat() if row.created_at else None,
                "status": row.status_code,
                "error": (row.error or "")[:200],
            }
            for row in recent_errors
        ],
        # in-process counters: reset on restart, and per worker process
        "cache": cache.stats(),
    }