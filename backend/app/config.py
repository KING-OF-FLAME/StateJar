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


@lru_cache
def get_settings() -> Settings:
    return Settings()
