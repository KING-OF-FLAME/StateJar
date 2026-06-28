"""Env-driven config. No hardcoded secrets (rule 5)."""
import os
from dataclasses import dataclass


@dataclass
class Config:
    database_url: str
    jwt_secret: str
    aes_key: str
    gliner2_url: str
    frontend_url: str


def load() -> Config:
    return Config(
        database_url=os.environ["DATABASE_URL"],
        jwt_secret=os.environ["JWT_SECRET"],
        aes_key=os.environ["AES_KEY"],
        gliner2_url=os.environ.get("GLINER2_URL", "http://localhost:8001"),
        frontend_url=os.environ.get("FRONTEND_URL", "http://localhost:5173"),
    )