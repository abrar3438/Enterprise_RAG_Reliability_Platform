"""
Centralized app configuration.

Why this exists: as the project grows (DB, Redis, LLM API keys, embedding
model names), you don't want magic strings/env lookups scattered across
files. Pydantic's BaseSettings reads from environment variables (and a
.env file) and validates types automatically.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RAG Reliability Platform"
    environment: str = "development"

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/ragdb"

    # LLM providers (filled in later)
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # SEC requires a real contact in the User-Agent. Set it in .env.
    sec_user_agent: str = ""


# Singleton: import this everywhere instead of re-instantiating Settings()
settings = Settings()