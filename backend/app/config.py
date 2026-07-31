"""Application settings loaded from environment / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    db_url: str = "mysql+pymysql://root:@localhost:3306/statejar"
    jwt_secret: str = "change-me"
    aes_key: str = "change-me-32-bytes-key-required!"
    # Locked down: only the StateJar frontend + local dev. Override in
    # production via CORS_ORIGINS='["https://statejar.example","..."]'
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://statejar.vercel.app",
        "https://statejar.com",
        "https://www.statejar.com",
    ]
    # --- extraction ---
    # "rules" (default, production) or "gliner" to additionally run the
    # optional neural layer from requirements-ml.txt. Anything unavailable
    # degrades silently back to rules.
    extractor_mode: str = "rules"
    # --- local (Ollama) models ---
    ollama_base_url: str = "http://localhost:11434"
    # Off by default so production statejar.com never advertises models that
    # only exist on a laptop; set SHOW_OLLAMA=true for local/offline demos.
    show_ollama: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
