"""StateJar FastAPI application entrypoint."""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.routes import router as auth_router
from app.config import get_settings
from app.llm.gateway import router as keys_router
from app.memory.routes import router as memory_router

settings = get_settings()

app = FastAPI(title="StateJar", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_v1 = APIRouter(prefix="/api/v1")


@api_v1.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


api_v1.include_router(auth_router)
api_v1.include_router(keys_router)
api_v1.include_router(memory_router)
app.include_router(api_v1)
