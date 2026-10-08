"""API-key check shared by the endpoints."""
import secrets

from fastapi import HTTPException

from app.core.config import settings


def check_api_key(x_api_key: str | None) -> None:
    """If API_KEY is set in the environment, callers must send it in the X-API-Key header."""
    expected = getattr(settings, "api_key", "")
    if not expected:
        return  # authentication disabled (local development)
    if not x_api_key or not secrets.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")