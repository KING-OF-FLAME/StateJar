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
    # --- rate limiting ---
    # On in production. Tests switch it off so unrelated suites are not
    # throttled; the rate-limit tests turn it back on explicitly.
    rate_limit_enabled: bool = True
    # --- extraction ---
    # "auto" (default) runs the GLiNER stage whenever the ML extras are
    # installed and degrades silently to the rule engine when they are not,
    # which is what happens on Railway. "gliner" is the explicit synonym.
    # "rules" forces the deterministic engine alone — use it when extraction
    # must be reproducible across machines.
    extractor_mode: str = "auto"
    # Tier 3: strict-JSON extraction through the user's own provider key, and
    # only for a long utterance the first two tiers barely understood. Off by
    # default because it spends the user's credit.
    extractor_llm_fallback: bool = False
    extractor_llm_model: str = "openrouter/openai/gpt-4o-mini"
    # --- retrieval ---
    # Off by default. When true (and sentence-transformers is installed) a
    # query the keyword intent map does not recognise falls back to embedding
    # similarity. Read path only — it cannot affect a handle.
    retriever_semantic: bool = False
    # --- provider endpoints ---
    # Overridable so a deployment can route through a proxy or gateway, and so
    # tests can point a provider at a local stub instead of the real host.
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    # --- local (Ollama) models ---
    ollama_base_url: str = "http://localhost:11434"
    # Off by default so production statejar.com never advertises models that
    # only exist on a laptop; set SHOW_OLLAMA=true for local/offline demos.
    show_ollama: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
