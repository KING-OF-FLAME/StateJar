"""StateJar FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.apikeys import router as apikeys_router
from app.auth.routes import router as auth_router
from app.config import get_settings
from app.llm.gateway import models_router
from app.llm.gateway import router as keys_router
from app.memory.routes import router as memory_router
from app.security import SecurityHeadersMiddleware, limiter
from app.version import git_sha

settings = get_settings()


def _ensure_tables() -> None:
    """Create any missing tables so saved data survives restarts.

    Best-effort: if the DB is unreachable (e.g. tests overriding get_db
    with their own engine), requests will surface the real error instead.
    """
    from app.apikeys import apikeys_metadata
    from app.auth.models import auth_metadata
    from app.database import engine
    from app.llm.gateway import llm_metadata
    from app.memory.audit import audit_metadata
    from app.memory.storage import metadata as storage_metadata

    try:
        from sqlalchemy import inspect, text

        # 004: memory_states dedup was global on handle, which silently
        # dropped saves whenever a second user (or session) produced the same
        # content-addressed handle — e.g. every fresh account running the
        # instant demo. Rebuild the key as a surrogate id + a unique index on
        # (handle, user_id, session_tag) before create_all sees the table.
        inspector = inspect(engine)
        if "memory_states" in inspector.get_table_names():
            columns = {c["name"] for c in inspector.get_columns("memory_states")}
            if "id" not in columns:
                with engine.begin() as conn:
                    if engine.dialect.name == "mysql":
                        conn.execute(text(
                            "ALTER TABLE memory_states DROP PRIMARY KEY, "
                            "ADD COLUMN id INT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST, "
                            "ADD UNIQUE KEY uq_memory_states_scope (handle, user_id, session_tag)"
                        ))
                    else:  # sqlite dev DBs: rebuild the table
                        conn.execute(text("ALTER TABLE memory_states RENAME TO memory_states_old"))
                        storage_metadata.tables["memory_states"].create(conn)
                        conn.execute(text(
                            "INSERT INTO memory_states (handle, parent_handle, state_json, "
                            "schema_version, norm_version, user_id, session_tag, created_at) "
                            "SELECT handle, parent_handle, state_json, schema_version, "
                            "norm_version, user_id, session_tag, created_at FROM memory_states_old"
                        ))
                        conn.execute(text("DROP TABLE memory_states_old"))

        for md in (auth_metadata, storage_metadata, audit_metadata, llm_metadata,
                   apikeys_metadata):
            md.create_all(engine, checkfirst=True)

        # create_all never alters existing tables; add columns introduced by
        # later migrations (003: audit_logs.session_tag) for DBs created
        # before them.
        inspector = inspect(engine)
        if "audit_logs" in inspector.get_table_names():
            columns = {c["name"] for c in inspector.get_columns("audit_logs")}
            if "session_tag" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE audit_logs ADD COLUMN session_tag VARCHAR(100) NULL")
                    )

        # 005: API key lifecycle. All nullable, so existing keys keep working —
        # a NULL expires_at reads as "never expires", which is what every key
        # issued before this migration was.
        if "api_keys" in inspector.get_table_names():
            columns = {c["name"] for c in inspector.get_columns("api_keys")}
            # literal statements, not built from parts: raw SQL in this repo is
            # always a constant (see test_no_dynamically_built_sql_in_app_code)
            additions = (
                ("label", text("ALTER TABLE api_keys ADD COLUMN label VARCHAR(100) NULL")),
                ("expires_at", text("ALTER TABLE api_keys ADD COLUMN expires_at DATETIME NULL")),
                ("last_used_at", text("ALTER TABLE api_keys ADD COLUMN last_used_at DATETIME NULL")),
            )
            missing = [stmt for name, stmt in additions if name not in columns]
            if missing:
                with engine.begin() as conn:
                    for statement in missing:
                        conn.execute(statement)

        # migration 006 — state_version. Rows written before the canonical
        # registry hold raw extractor keys; they default to 1 and are read
        # forward rather than rewritten, because rewriting state_json would
        # invalidate the handle that addresses it.
        if "memory_states" in inspector.get_table_names():
            columns = {c["name"] for c in inspector.get_columns("memory_states")}
            if "state_version" not in columns:
                with engine.begin() as conn:
                    conn.execute(text(
                        "ALTER TABLE memory_states "
                        "ADD COLUMN state_version INT NOT NULL DEFAULT 1"
                    ))

        # migration 007 — the Ollama card became two. A saved config that
        # carries an API key was always describing a remote daemon, so it
        # moves to the remote provider; one without a key is a local daemon
        # and stays. Nobody loses a setting either way.
        if "provider_keys" in inspector.get_table_names():
            _split_ollama_configs(engine)
    except Exception:  # noqa: BLE001 — DB down at boot must not kill the app
        pass


def _split_ollama_configs(engine: Any) -> None:
    """Re-file keyed Ollama configs under `ollama_remote`. Idempotent.

    Read-and-rewrite rather than a bare UPDATE, because the stored value is
    AES-encrypted: only the application can tell whether a row carries a key,
    and therefore which of the two cards it belongs to.
    """
    from sqlalchemy import select

    from app.llm.gateway import decrypt_key, provider_keys
    from app.llm.providers import OllamaProvider

    with engine.begin() as conn:
        rows = conn.execute(
            select(provider_keys.c.id, provider_keys.c.encrypted_key)
            .where(provider_keys.c.provider == "ollama")
        ).mappings().all()

        for row in rows:
            try:
                _, api_key = OllamaProvider.parse_config(decrypt_key(row["encrypted_key"]))
            except Exception:  # noqa: BLE001 — an unreadable row is left alone
                continue
            if not api_key:
                continue          # no key: a local daemon, already on the right card
            conn.execute(
                provider_keys.update()
                .where(provider_keys.c.id == row["id"])
                .values(provider="ollama_remote")
            )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _ensure_tables()
    yield


app = FastAPI(title="StateJar", version="0.1.0", lifespan=_lifespan)

limiter.enabled = settings.rate_limit_enabled
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# outermost middleware runs last on the way out, so these headers land on
# every response including CORS preflights and rate-limit rejections
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

api_v1 = APIRouter(prefix="/api/v1")


@api_v1.get("/health")
def health() -> dict[str, str]:
    """Liveness plus the commit this instance is running.

    `version` makes "is production actually running local main?" a one-line
    check rather than an assumption.
    """
    return {"status": "ok", "version": git_sha()}


api_v1.include_router(auth_router)
api_v1.include_router(apikeys_router)
api_v1.include_router(keys_router)
api_v1.include_router(models_router)
api_v1.include_router(memory_router)
app.include_router(api_v1)
