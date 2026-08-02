"""Tests for the LLM gateway: encryption, key endpoint, chat, providers."""

import os
from collections.abc import Generator

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tests.conftest import fake_key
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
    key = fake_key("or-abc789")
    blob = encrypt_key(key)
    assert blob != key.encode()
    assert decrypt_key(blob) == key
    # nonce is random: same plaintext → different ciphertext
    assert encrypt_key(key) != blob


def test_save_provider_key_masks_key(client: TestClient) -> None:
    headers = _auth_headers(client)
    resp = client.post(
        "/api/v1/keys/provider",
        json={"provider": "openrouter", "api_key": fake_key("or-abc9876")},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body == {"provider": "openrouter", "key_last4": "9876", "saved": True}
    assert "not-a-real-key" not in str(body)


def test_save_key_requires_auth(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/keys/provider", json={"provider": "openrouter", "api_key": fake_key("or-abc123")}
    )
    assert resp.status_code == 401


def test_unknown_provider_rejected(client: TestClient) -> None:
    headers = _auth_headers(client)
    resp = client.post(
        "/api/v1/keys/provider",
        json={"provider": "notreal", "api_key": fake_key("unknown-provider")},
        headers=headers,
    )
    assert resp.status_code == 422


def test_list_keys_empty(client: TestClient) -> None:
    headers = _auth_headers(client)
    resp = client.get("/api/v1/keys/provider", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_keys_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/keys/provider").status_code == 401


def test_list_keys_returns_latest_per_provider_masked(client: TestClient) -> None:
    headers = _auth_headers(client)
    for key in (fake_key("or-old-1111"), fake_key("or-new-2222")):
        client.post(
            "/api/v1/keys/provider",
            json={"provider": "openrouter", "api_key": key},
            headers=headers,
        )
    resp = client.get("/api/v1/keys/provider", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    # only the latest openrouter key, masked to last 4 chars
    assert len(body) == 1
    assert body[0]["provider"] == "openrouter"
    assert body[0]["key_last4"] == "2222"
    assert body[0]["created_at"]
    assert "not-a-real-key" not in str(body)


def test_list_keys_scoped_to_current_user(client: TestClient) -> None:
    headers_a = _auth_headers(client)
    client.post(
        "/api/v1/keys/provider",
        json={"provider": "openrouter", "api_key": fake_key("or-usera-7777")},
        headers=headers_a,
    )
    client.post("/api/v1/auth/signup", json={"email": "b@example.com", "password": "s3cretpass"})
    token_b = client.post(
        "/api/v1/auth/login", json={"email": "b@example.com", "password": "s3cretpass"}
    ).json()["access_token"]
    resp = client.get(
        "/api/v1/keys/provider", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.json() == []


def test_build_system_context() -> None:
    ctx = build_system_context("shm_" + "a" * 40, {"preferences": {"contact_mode": "email"}})
    assert ctx.startswith("Known user state (retrieved via StateJar handle shm_")
    assert '"contact_mode": "email"' in ctx


def test_every_provider_implements_the_shared_interface() -> None:
    """All five are real now — see tests/test_providers.py for their wire calls."""
    for name in ("openrouter", "openai", "anthropic", "gemini", "ollama"):
        provider = get_provider(name)
        assert callable(provider.chat)
        assert callable(provider.list_models)
        assert provider.label


def test_demo_provider_needs_no_key_and_no_network() -> None:
    db = _TestSession()
    try:
        # no provider key saved for this user — demo must still answer
        result = chat(
            db, user_id=42, model="scripted-demo",
            system_context="s", user_message="Stack: React + Tailwind, dark theme",
            provider="demo",
        )
    finally:
        db.close()
    assert "React + Tailwind" in result["content"]
    assert result["model"] == "scripted-demo"


def test_demo_provider_scripted_steps() -> None:
    """Canned replies track the playground's web-dev scenario."""
    demo = get_provider("demo")
    assert "React + Tailwind" in demo.chat("", "m", "s", "Stack: React + Tailwind")["content"]
    assert "Pricing section" in demo.chat("", "m", "s", "Now add a pricing section")["content"]
    assert "conflict" in demo.chat("", "m", "s", "Use shadcn/ui")["content"]
    assert "scripted demo" in demo.chat("", "m", "s", "hello there")["content"]


@respx.mock
def test_chat_calls_openrouter_with_user_key(client: TestClient) -> None:
    headers = _auth_headers(client)
    client.post(
        "/api/v1/keys/provider",
        json={"provider": "openrouter", "api_key": fake_key("or-1234")},
        headers=headers,
    )
    route = respx.post(OpenRouterProvider.BASE_URL).mock(
        return_value=Response(
            200,
            json={
                "model": "meta-llama/llama-3.3-70b-instruct:free",
                "choices": [{"message": {"role": "assistant", "content": "Hello Ayaan!"}}],
                "usage": {"prompt_tokens": 30, "completion_tokens": 12, "total_tokens": 42},
            },
        )
    )
    db = _TestSession()
    try:
        result = chat(
            db,
            user_id=1,
            # a vendor prefix that is not a provider name stays on OpenRouter
            model="meta-llama/llama-3.3-70b-instruct:free",
            system_context=build_system_context("shm_" + "a" * 40, {"facts": {"name": "Ayaan"}}),
            user_message="Greet me",
        )
    finally:
        db.close()
    assert result["content"] == "Hello Ayaan!"
    assert result["usage"]["total_tokens"] == 42
    sent = route.calls.last.request
    assert sent.headers["authorization"] == f"Bearer {fake_key('or-1234')}"
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


# --- /models catalog ----------------------------------------------------------

from app.llm import gateway as gw  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_models_cache() -> None:
    gw.clear_models_cache()


_CATALOG = {
    "data": [
        {
            "id": "big/free-model:free",
            "name": "Big Free Model",
            "context_length": 200000,
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"output_modalities": ["text"]},
        },
        {
            "id": "small/free-model:free",
            "name": "Small Free Model",
            "context_length": 8192,
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"modality": "text->text"},
        },
        {
            "id": "openai/gpt-4o",
            "name": "GPT-4o",
            "context_length": 128000,
            "pricing": {"prompt": "0.0000025", "completion": "0.00001"},
        },
        {
            "id": "media/free-music-model",
            "name": "Free Music Model",
            "context_length": 500000,
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"output_modalities": ["audio"]},
        },
    ]
}


def test_models_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/models").status_code == 401


def test_models_empty_without_any_key(client: TestClient) -> None:
    """No keys, no groups — the picker then prompts for one."""
    resp = client.get("/api/v1/models", headers=_auth_headers(client))
    assert resp.status_code == 200
    body = resp.json()
    assert body["groups"] == []
    assert body["source"] == "fallback"


@respx.mock
def test_models_groups_openrouter_free_and_paid(client: TestClient) -> None:
    headers = _auth_headers(client)
    client.post("/api/v1/keys/provider",
                json={"provider": "openrouter", "api_key": fake_key("or-1234")},
                headers=headers)
    respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=Response(200, json=_CATALOG))

    body = client.get("/api/v1/models", headers=headers).json()
    assert body["source"] == "live"
    assert [g["provider"] for g in body["groups"]] == ["openrouter"]
    group = body["groups"][0]
    assert group["label"] == "OpenRouter"
    # free, biggest context first; the audio-only freebie is excluded
    assert [m["id"] for m in group["free"]] == ["big/free-model:free", "small/free-model:free"]
    assert all(m["is_free"] for m in group["free"])
    assert group["free"][0]["context_length"] == 200000
    assert group["paid"] and not any(m["is_free"] for m in group["paid"])


@respx.mock
def test_models_cached_per_user_for_an_hour(client: TestClient) -> None:
    headers = _auth_headers(client)
    client.post("/api/v1/keys/provider",
                json={"provider": "openrouter", "api_key": fake_key("or-1234")},
                headers=headers)
    route = respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=Response(200, json=_CATALOG))

    client.get("/api/v1/models", headers=headers)
    client.get("/api/v1/models", headers=headers)
    assert route.call_count == 1


@respx.mock
def test_saving_a_key_invalidates_the_cache(client: TestClient) -> None:
    """A rotated key must be used immediately, not in an hour."""
    headers = _auth_headers(client)
    client.post("/api/v1/keys/provider",
                json={"provider": "openrouter", "api_key": fake_key("or-1234")},
                headers=headers)
    route = respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=Response(200, json=_CATALOG))

    client.get("/api/v1/models", headers=headers)
    client.post("/api/v1/keys/provider",
                json={"provider": "openrouter", "api_key": fake_key("or-rotated-9999")},
                headers=headers)
    client.get("/api/v1/models", headers=headers)
    assert route.call_count == 2
    assert route.calls.last.request.headers["authorization"] == (
        f"Bearer {fake_key('or-rotated-9999')}")


@respx.mock
def test_one_failing_provider_does_not_break_the_others(client: TestClient) -> None:
    """The whole point of grouping: a dead provider costs only its own group."""
    headers = _auth_headers(client)
    for provider, key in (("openrouter", fake_key("or-1234")), ("openai", fake_key("openai-testkey"))):
        client.post("/api/v1/keys/provider",
                    json={"provider": provider, "api_key": key}, headers=headers)

    respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=Response(200, json=_CATALOG))
    respx.get("https://api.openai.com/v1/models").mock(
        return_value=Response(500, json={"error": {"message": "upstream on fire"}}))

    body = client.get("/api/v1/models", headers=headers).json()
    groups = {g["provider"]: g for g in body["groups"]}
    assert set(groups) == {"openrouter", "openai"}
    assert groups["openrouter"]["free"]                 # unaffected
    assert groups["openai"]["free"] == [] and groups["openai"]["paid"] == []
    assert "upstream on fire" in groups["openai"]["error"]
    assert body["source"] == "live"                     # one good provider is enough


@respx.mock
def test_catalog_error_never_contains_the_key(client: TestClient) -> None:
    headers = _auth_headers(client)
    client.post("/api/v1/keys/provider",
                json={"provider": "openai", "api_key": fake_key("openai-supersecret")},
                headers=headers)
    respx.get("https://api.openai.com/v1/models").mock(
        return_value=Response(401, json={"error": {
            # the provider quotes the offending credential straight back
            "message": f"bad key {fake_key('openai-supersecret')}"}}))

    body = client.get("/api/v1/models", headers=headers).json()
    error = body["groups"][0]["error"]
    assert fake_key("openai-supersecret") not in error
    assert "***" in error and "rejected the API key" in error


def test_delete_provider_key(client: TestClient) -> None:
    headers = _auth_headers(client)
    client.post("/api/v1/keys/provider",
                json={"provider": "openai", "api_key": fake_key("openai-testkey")}, headers=headers)
    listed = client.get("/api/v1/keys/provider", headers=headers).json()
    assert [k["provider"] for k in listed] == ["openai"]

    resp = client.request("DELETE", "/api/v1/keys/provider/openai", headers=headers)
    assert resp.status_code == 200 and resp.json()["removed"] is True
    assert client.get("/api/v1/keys/provider", headers=headers).json() == []
    assert client.request(
        "DELETE", "/api/v1/keys/provider/openai", headers=headers).status_code == 404


def test_saving_a_key_twice_replaces_it(client: TestClient) -> None:
    """A rotated key must not leave the old one usable."""
    headers = _auth_headers(client)
    for key in (fake_key("openai-first-1"), fake_key("openai-second-2")):
        client.post("/api/v1/keys/provider",
                    json={"provider": "openai", "api_key": key}, headers=headers)
    listed = client.get("/api/v1/keys/provider", headers=headers).json()
    assert len(listed) == 1
    assert listed[0]["key_last4"] == fake_key("openai-second-2")[-4:]

    db = _TestSession()
    try:
        assert gw._get_user_key(db, 1, "openai") == fake_key("openai-second-2")
        rows = db.execute(
            select(gw.provider_keys).where(gw.provider_keys.c.provider == "openai")
        ).mappings().all()
        assert len(rows) == 1  # superseded row deleted, not shadowed
    finally:
        db.close()


@pytest.mark.parametrize("provider", ["openrouter", "openai", "anthropic", "gemini", "ollama"])
def test_key_roundtrip_per_provider(client: TestClient, provider: str) -> None:
    headers = _auth_headers(client)
    secret = f"secret-for-{provider}-1234"
    resp = client.post("/api/v1/keys/provider",
                       json={"provider": provider, "api_key": secret}, headers=headers)
    assert resp.status_code == 201
    assert secret not in resp.text                        # never echoed back
    assert resp.json()["key_last4"] == secret[-4:]
    assert secret not in client.get("/api/v1/keys/provider", headers=headers).text

    db = _TestSession()
    try:
        assert gw._get_user_key(db, 1, provider) == secret   # decrypts intact
    finally:
        db.close()


def test_key_accepts_either_field_name(client: TestClient) -> None:
    """`key` is the documented name; `api_key` is what the console has always sent."""
    headers = _auth_headers(client)
    resp = client.post("/api/v1/keys/provider",
                       json={"provider": "gemini", "key": "gemini-secret-1234"},
                       headers=headers)
    assert resp.status_code == 201 and resp.json()["key_last4"] == "1234"
