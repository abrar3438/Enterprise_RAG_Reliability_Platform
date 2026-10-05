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
    database_url: str = ""  # Set in .env

    # SEC requires a real contact in the User-Agent. Set it in .env.
    sec_user_agent: str = ""

    # CraftX LLM settings
    craftx_api_key: str = ""  # Set in .env
    craftx_endpoint: str = "https://api.craftx.corecraftsolutions.com/api/v1/chat/completions"
    craftx_model: str = "gpt oss 120b"

    verify_answers: bool = False

# Singleton: import this everywhere instead of re-instantiating Settings()
settings = Settings()