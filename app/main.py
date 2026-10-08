# """
# Entry point. Run with: uvicorn app.main:app --reload

# Why FastAPI: async-native (matters once we're calling LLM APIs and DB
# concurrently), automatic request validation via Pydantic, and free
# interactive docs at /docs.
# """
# from fastapi import FastAPI

# from app.core.config import settings

# app = FastAPI(title=settings.app_name)


# @app.get("/health")
# def health_check():
#     """
#     Every production service needs this. Deployment platforms (Render,
#     Fly.io, k8s) ping this endpoint to know if your service is alive.
#     """
#     return {"status": "ok", "environment": settings.environment}

# """FastAPI app entrypoint."""
# import logging
# from contextlib import asynccontextmanager
# from fastapi import FastAPI
# from app.core.config import settings
# from app.routers.query import router as query_router
# from app.routers.stats import router as stats_router

# # Setup basic logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     # Load models and build BM25 index on startup so the first request isn't slow
#     logger.info("Loading embedding model, reranker, and BM25 index...")
#     from app.services.embeddings import get_model
#     from app.services.retrieval import get_reranker, _bm25_index
#     get_model()
#     get_reranker()
#     _bm25_index()
#     logger.info("Models loaded and ready.")
#     yield
#     # Clean up (if needed)
#     logger.info("Shutting down.")

# app = FastAPI(
#     title=settings.app_name,
#     lifespan=lifespan
# )

# # Keep /health
# @app.get("/health")
# def health_check():
#     return {"status": "ok", "environment": settings.environment}

# # Register the query router
# app.include_router(query_router)
# app.include_router(stats_router)

"""FastAPI app entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.routers.query import router as query_router
from app.routers.system import router as system_router
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load models and build the BM25 index on startup so the first request isn't slow
    logger.info("Loading embedding model, reranker, and BM25 index...")
    from app.services.embeddings import get_model
    from app.services.retrieval import get_reranker, _bm25_index

    get_model()
    get_reranker()
    _bm25_index()
    logger.info("Models loaded and ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(title=settings.app_name, lifespan=lifespan)
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")

# /health and /stats live in system.py (/health checks the database)
app.include_router(system_router)
app.include_router(query_router)