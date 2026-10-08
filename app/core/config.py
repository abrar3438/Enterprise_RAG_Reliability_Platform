"""
Centralized app configuration.

Pydantic's BaseSettings reads from environment variables and a .env file,
and validates types automatically.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RAG Reliability Platform"
    environment: str = "development"

    # Database
    database_url: str = ""  # set in .env

    # SEC requires a real contact in the User-Agent. Set it in .env.
    sec_user_agent: str = ""

    # CraftX LLM settings
    craftx_api_key: str = ""  # set in .env
    craftx_endpoint: str = "https://api.craftx.corecraftsolutions.com/api/v1/chat/completions"
    craftx_model: str = "gpt oss 120b"

    # API access: empty means no key is required
    api_key: str = ""

    # Answer verification pass (off in v1: approved a known wrong answer 12 of 12 times)
    verify_answers: bool = False

    # Context packing (off in v1: retrieval gain not confirmed at answer level)
    packing_enabled: bool = False
    packing_char_budget: int = 6000

    # Public demo limits (step 4)
    daily_query_cap: int = 200  # 0 disables the daily cap


# Singleton: import this everywhere instead of re-instantiating Settings()
settings = Settings()