"""
config/settings.py
──────────────────
Central configuration via Pydantic-Settings.
All values are loaded from .env (or environment variables).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017/fashion_ecommerce"
    db_name: str = "fashion_ecommerce"

    # Gemini (https://aistudio.google.com)
    gemini_api_key: str = "your_gemini_api_key_here"
    gemini_model: str = "gemini-2.0-flash"

    # Groq — free alternative (https://console.groq.com)
    groq_api_key: str = ""

    # Which LLM provider to use: "gemini" or "groq"
    # Set to "groq" if Gemini quota is exhausted
    llm_provider: str = "gemini"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # Security
    admin_api_key: str = "change-this-in-production"

    # Agent
    agent_max_retries: int = 3
    agent_temperature: float = 0.1


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """Force-clear the cache and reload from .env. Call after editing .env."""
    get_settings.cache_clear()
    return get_settings()
