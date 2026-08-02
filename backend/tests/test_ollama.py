"""Tests for the local Ollama provider and its keyless gateway routing."""

from collections.abc import Generator

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.models import auth_metadata
from app.config import get_settings
from app.database import get_db
from app.llm import gateway
from app.llm.gateway import llm_metadata
from app.llm.providers import OllamaProvider, ProviderUnavailableError, get_provider
from app.main import app
from app.memory.audit import audit_metadata
from app.memory.storage import metadata as storage_metadata

_engine = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
_TestSession = sessionmaker(bind=_engine)

OLLAMA_URL = "http://localhost:11434/api/chat"

# A representative /api/chat response (stream=false).
OLLAMA_REPLY = {
    "model": "llama3.2",
    "message": {"role": "assistant", "content": "Your budget is ₹2000."},
    "done": True,
    "prompt_eval_count": 41,
    "eval_count": 12,
}


def _test_db() -> Generator[Session, None, None]:
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def client() -> Generator[TestClient, None, None]:
    for md in (auth_metadata, storage_metadata, audit_metadata, llm_metadata):
        md.drop_all(_engine)
        md.create_all(_engine)
    app.dependency_overrides[get_db] = _test_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_settings() -> Generator[None, None, None]:
    """Settings are cached; env tweaks in a test must not leak into the next."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _auth_headers(client: TestClient) -> dict[str, str]:
    client.post("/api/v1/auth/signup", json={"email": "o@example.com", "password": "s3cretpass"})
    token = client.post(
        "/api/v1/auth/login", json={"email": "o@example.com", "password": "s3cretpass"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- provider ----------------------------------------------------------------


@respx.mock
def test_provider_posts_expected_payload() -> None:
    route = respx.post(OLLAMA_URL).mock(return_value=Response(200, json=OLLAMA_REPLY))
    result = OllamaProvider().chat("", "llama3.2", "known state", "what is my budget?")

    sent = route.calls.last.request
    body = sent.read().decode()
    assert '"model":"llama3.2"' in body.replace(" ", "")
    assert '"stream":false' in body.replace(" ", "")
    assert "known state" in body
    assert "what is my budget?" in body
    assert result["text"] == "Your budget is ₹2000."


@respx.mock
def test_provider_maps_token_counts_and_latency() -> None:
    respx.post(OLLAMA_URL).mock(return_value=Response(200, json=OLLAMA_REPLY))
    result = OllamaProvider().chat("", "llama3.2", "s", "u")

    assert result["tokens_in"] == 41       # prompt_eval_count
    assert result["tokens_out"] == 12      # eval_count
    assert isinstance(result["latency_ms"], int) and result["latency_ms"] >= 0
    # superset of the shared provider shape, so existing callers keep working
    assert result["content"] == result["text"]
    assert result["model"] == "llama3.2"
    assert result["usage"]["total_tokens"] == 53


@respx.mock
def test_provider_missing_counts_default_to_zero() -> None:
    respx.post(OLLAMA_URL).mock(
        return_value=Response(200, json={"message": {"content": "hi"}})
    )
    result = OllamaProvider().chat("", "llama3.2", "s", "u")
    assert result["tokens_in"] == 0
    assert result["tokens_out"] == 0


@respx.mock
def test_connection_refused_gives_actionable_message() -> None:
    respx.post(OLLAMA_URL).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(ProviderUnavailableError) as exc:
        OllamaProvider().chat("", "llama3.2", "s", "u")
    assert "Ollama not reachable at http://localhost:11434" in str(exc.value)
    assert "ollama serve" in str(exc.value)


@respx.mock
def test_base_url_comes_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://gpu-box:9999/")
    get_settings.cache_clear()
    route = respx.post("http://gpu-box:9999/api/chat").mock(
        return_value=Response(200, json=OLLAMA_REPLY)
    )
    OllamaProvider().chat("", "llama3.2", "s", "u")
    assert route.called  # trailing slash trimmed, env honoured


def test_registry_exposes_ollama() -> None:
    assert isinstance(get_provider("ollama"), OllamaProvider)


# --- gateway routing ----------------------------------------------------------


@respx.mock
def test_ollama_prefix_routes_to_provider_with_prefix_stripped() -> None:
    route = respx.post(OLLAMA_URL).mock(return_value=Response(200, json=OLLAMA_REPLY))
    db = _TestSession()
    try:
        result = gateway.chat(
            db, user_id=1, model="ollama/llama3.2",
            system_context="s", user_message="u",
        )
    finally:
        db.close()

    body = route.calls.last.request.read().decode().replace(" ", "")
    assert '"model":"llama3.2"' in body   # prefix stripped before dispatch
    assert "ollama/" not in body
    assert result["provider"] == "ollama"


@respx.mock
def test_ollama_needs_no_provider_key() -> None:
    """A user with zero saved keys can still use a local model."""
    respx.post(OLLAMA_URL).mock(return_value=Response(200, json=OLLAMA_REPLY))
    db = _TestSession()
    try:
        # same user id raises LookupError for a hosted model...
        with pytest.raises(LookupError):
            gateway.chat(db, user_id=999, model="openai/gpt-4o-mini",
                         system_context="s", user_message="u")
        # ...but sails through for a local one
        result = gateway.chat(db, user_id=999, model="ollama/qwen2.5:3b",
                              system_context="s", user_message="u")
    finally:
        db.close()
    assert result["text"] == "Your budget is ₹2000."


@respx.mock
def test_tagged_model_names_survive_prefix_strip() -> None:
    route = respx.post(OLLAMA_URL).mock(return_value=Response(200, json=OLLAMA_REPLY))
    db = _TestSession()
    try:
        gateway.chat(db, user_id=1, model="ollama/qwen2.5:3b",
                     system_context="s", user_message="u")
    finally:
        db.close()
    body = route.calls.last.request.read().decode().replace(" ", "")
    assert '"model":"qwen2.5:3b"' in body  # the ":3b" tag is not mangled


def test_non_ollama_models_keep_openrouter_behaviour() -> None:
    db = _TestSession()
    try:
        with pytest.raises(LookupError, match="OpenRouter API key"):
            gateway.chat(db, user_id=1, model="meta-llama/llama-3.3-70b-instruct:free",
                         system_context="s", user_message="u")
    finally:
        db.close()


# --- audit + catalog ----------------------------------------------------------


@respx.mock
def test_chat_route_audits_provider_as_ollama(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    respx.post(OLLAMA_URL).mock(return_value=Response(200, json=OLLAMA_REPLY))
    headers = _auth_headers(client)
    client.post("/api/v1/memory/ingest",
                json={"session_tag": "s1", "text": "My budget is 2000"}, headers=headers)

    resp = client.post("/api/v1/chat", headers=headers, json={
        "session_tag": "s1", "query": "what is my budget?", "model": "ollama/llama3.2",
    })
    assert resp.status_code == 200, resp.text

    entries = client.get("/api/v1/audit?limit=5", headers=headers).json()["entries"]
    latest = entries[0]
    assert latest["provider"] == "ollama"
    assert latest["model"] == "llama3.2"


@respx.mock
def test_chat_route_surfaces_ollama_down_message(client: TestClient) -> None:
    respx.post(OLLAMA_URL).mock(side_effect=httpx.ConnectError("refused"))
    headers = _auth_headers(client)
    client.post("/api/v1/memory/ingest",
                json={"session_tag": "s1", "text": "My budget is 2000"}, headers=headers)

    resp = client.post("/api/v1/chat", headers=headers, json={
        "session_tag": "s1", "query": "budget?", "model": "ollama/llama3.2",
    })
    assert resp.status_code == 502
    assert "is `ollama serve` running?" in resp.json()["detail"]


def test_models_hides_local_group_by_default(client: TestClient) -> None:
    gateway.clear_models_cache()
    body = client.get("/api/v1/models", headers=_auth_headers(client)).json()
    assert [g["provider"] for g in body["groups"]] == []


@respx.mock
def test_models_shows_local_group_when_enabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ollama is the one provider that appears without a saved key."""
    monkeypatch.setenv("SHOW_OLLAMA", "true")
    get_settings.cache_clear()
    gateway.clear_models_cache()
    respx.get("http://localhost:11434/api/tags").mock(return_value=Response(
        200, json={"models": [{"name": "llama3.2"}, {"name": "qwen2.5:3b"}]}))

    body = client.get("/api/v1/models", headers=_auth_headers(client)).json()
    local = next(g for g in body["groups"] if g["provider"] == "ollama")
    # namespaced so /chat routes them back to the daemon, and free because
    # local inference costs nothing
    assert [m["id"] for m in local["free"]] == ["ollama/llama3.2", "ollama/qwen2.5:3b"]
    assert local["paid"] == []


@respx.mock
def test_ollama_http_error_names_ollama_not_openrouter(client: TestClient) -> None:
    """A local-model failure must not be blamed on OpenRouter."""
    respx.post(OLLAMA_URL).mock(
        return_value=Response(500, json={"error": "model requires more system memory"})
    )
    headers = _auth_headers(client)
    client.post("/api/v1/memory/ingest",
                json={"session_tag": "s1", "text": "My budget is 2000"}, headers=headers)

    resp = client.post("/api/v1/chat", headers=headers, json={
        "session_tag": "s1", "query": "budget?", "model": "ollama/llama3.2",
    })
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    # Ollama's {"error": "<string>"} shape is surfaced verbatim...
    assert "model requires more system memory" in detail
    # ...and the message never blames the provider that was not called
    assert "openrouter" not in detail.lower()


def test_resolve_provider() -> None:
    assert gateway.resolve_provider("ollama/llama3.2") == "ollama"
    assert gateway.resolve_provider("ollama/qwen2.5:3b", "openrouter") == "ollama"
    # a provider-named prefix now routes to that provider...
    assert gateway.resolve_provider("openai/gpt-4o-mini") == "openai"
    assert gateway.resolve_provider("anthropic/claude-sonnet-4-6") == "anthropic"
    assert gateway.resolve_provider("gemini/gemini-2.5-flash") == "gemini"
    # ...while a plain vendor prefix stays with OpenRouter
    assert gateway.resolve_provider("meta-llama/llama-3.3-70b-instruct:free") == "openrouter"
    assert gateway.resolve_provider("some-custom-id") == "openrouter"
    assert gateway.resolve_provider("scripted-demo", "demo") == "demo"
