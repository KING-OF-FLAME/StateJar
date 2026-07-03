"""Tests for the LLM gateway: encryption, key endpoint, chat, providers."""

import os
from collections.abc import Generator

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.models import auth_metadata
from app.database import get_db
from app.llm.gateway import (
    build_system_context,
    chat,
    decrypt_key,
    encrypt_key,
    llm_metadata,
)
from app.llm.providers import OpenRouterProvider, get_provider
from app.main import app

_engine = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
_TestSession = sessionmaker(bind=_engine)


def _test_db() -> Generator[Session, None, None]:
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def client() -> Generator[TestClient, None, None]:
    for md in (auth_metadata, llm_metadata):
        md.drop_all(_engine)
        md.create_all(_engine)
    app.dependency_overrides[get_db] = _test_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _auth_headers(client: TestClient) -> dict[str, str]:
    client.post("/api/v1/auth/signup", json={"email": "a@example.com", "password": "s3cretpass"})
    token = client.post(
        "/api/v1/auth/login", json={"email": "a@example.com", "password": "s3cretpass"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_encrypt_decrypt_roundtrip() -> None:
    key = "sk-or-v1-abc123xyz789"
    blob = encrypt_key(key)
    assert blob != key.encode()
    assert decrypt_key(blob) == key
    # nonce is random: same plaintext → different ciphertext
    assert encrypt_key(key) != blob


def test_save_provider_key_masks_key(client: TestClient) -> None:
    headers = _auth_headers(client)
    resp = client.post(
        "/api/v1/keys/provider",
        json={"provider": "openrouter", "api_key": "sk-or-v1-abc123xyz9876"},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body == {"provider": "openrouter", "key_last4": "9876", "saved": True}
    assert "sk-or" not in str(body)


def test_save_key_requires_auth(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/keys/provider", json={"provider": "openrouter", "api_key": "sk-or-v1-abc123"}
    )
    assert resp.status_code == 401


def test_unknown_provider_rejected(client: TestClient) -> None:
    headers = _auth_headers(client)
    resp = client.post(
        "/api/v1/keys/provider",
        json={"provider": "notreal", "api_key": "sk-something-123"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_build_system_context() -> None:
    ctx = build_system_context("shm_" + "a" * 40, {"preferences": {"contact_mode": "email"}})
    assert ctx.startswith("Known user state (retrieved via StateJar handle shm_")
    assert '"contact_mode": "email"' in ctx


def test_placeholder_providers_raise() -> None:
    for name in ("openai", "anthropic", "gemini", "ollama"):
        with pytest.raises(NotImplementedError):
            get_provider(name).chat("k", "m", "s", "u")


@respx.mock
def test_chat_calls_openrouter_with_user_key(client: TestClient) -> None:
    headers = _auth_headers(client)
    client.post(
        "/api/v1/keys/provider",
        json={"provider": "openrouter", "api_key": "sk-or-v1-testkey1234"},
        headers=headers,
    )
    route = respx.post(OpenRouterProvider.BASE_URL).mock(
        return_value=Response(
            200,
            json={
                "model": "openai/gpt-4o-mini",
                "choices": [{"message": {"role": "assistant", "content": "Hello Ayaan!"}}],
                "usage": {"total_tokens": 42},
            },
        )
    )
    db = _TestSession()
    try:
        result = chat(
            db,
            user_id=1,
            model="openai/gpt-4o-mini",
            system_context=build_system_context("shm_" + "a" * 40, {"facts": {"name": "Ayaan"}}),
            user_message="Greet me",
        )
    finally:
        db.close()
    assert result["content"] == "Hello Ayaan!"
    assert result["usage"]["total_tokens"] == 42
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer sk-or-v1-testkey1234"
    assert b"StateJar handle" in sent.content


def test_chat_without_saved_key_raises() -> None:
    db = _TestSession()
    try:
        with pytest.raises(LookupError):
            chat(db, user_id=999, model="m", system_context="s", user_message="u")
    finally:
        db.close()


@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="set OPENROUTER_API_KEY to run the live integration test",
)
def test_live_openrouter_chat() -> None:
    provider = OpenRouterProvider()
    result = provider.chat(
        os.environ["OPENROUTER_API_KEY"],
        "openai/gpt-4o-mini",
        "You are a test. Reply with one word.",
        "Say OK",
    )
    assert isinstance(result["content"], str) and result["content"]
