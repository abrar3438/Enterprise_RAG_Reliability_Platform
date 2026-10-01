"""
Entry point. Run with: uvicorn app.main:app --reload

Why FastAPI: async-native (matters once we're calling LLM APIs and DB
concurrently), automatic request validation via Pydantic, and free
interactive docs at /docs.
"""
from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(title=settings.app_name)


@app.get("/health")
def health_check():
    """
    Every production service needs this. Deployment platforms (Render,
    Fly.io, k8s) ping this endpoint to know if your service is alive.
    """
    return {"status": "ok", "environment": settings.environment}