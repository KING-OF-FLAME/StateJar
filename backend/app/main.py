"""StateJar FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.routes import router as auth_router
from app.config import get_settings
from app.llm.gateway import models_router
from app.llm.gateway import router as keys_router
from app.memory.routes import router as memory_router

settings = get_settings()


def _ensure_tables() -> None:
    """Create any missing tables so saved data survives restarts.

    Best-effort: if the DB is unreachable (e.g. tests overriding get_db
    with their own engine), requests will surface the real error instead.
    """
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

        for md in (auth_metadata, storage_metadata, audit_metadata, llm_metadata):
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
    except Exception:  # noqa: BLE001 — DB down at boot must not kill the app
        pass


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _ensure_tables()
    yield


app = FastAPI(title="StateJar", version="0.1.0", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

api_v1 = APIRouter(prefix="/api/v1")


@api_v1.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


api_v1.include_router(auth_router)
api_v1.include_router(keys_router)
api_v1.include_router(models_router)
api_v1.include_router(memory_router)
app.include_router(api_v1)
