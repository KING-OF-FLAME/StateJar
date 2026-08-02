"""Per-provider wire behaviour: request shape, token mapping, error safety.

Each provider speaks a different dialect — Anthropic puts the system prompt in
a top-level field, Gemini uses contents/parts and a header credential — so
these assert the actual bytes sent, not just that a call happened.
"""

import json
from typing import Any

import pytest
import respx
from httpx import Response

from app.config import get_settings
from app.llm.providers import (
    AnthropicProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
    ProviderError,
    ProviderUnavailableError,
    get_provider,
)

SYSTEM = "Known user state (retrieved via StateJar handle shm_abc): {}"
USER = "Now add a pricing section."

OPENAI_CHAT = "https://api.openai.com/v1/chat/completions"
OPENAI_MODELS = "https://api.openai.com/v1/models"
ANTHROPIC_CHAT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODELS = "https://api.anthropic.com/v1/models"
GEMINI_MODELS = "https://generativelanguage.googleapis.com/v1beta/models"
OLLAMA_CHAT = "http://localhost:11434/api/chat"
OLLAMA_TAGS = "http://localhost:11434/api/tags"


@pytest.fixture(autouse=True)
def _clean_settings() -> Any:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- OpenAI -------------------------------------------------------------------


@respx.mock
def test_openai_chat_shape_and_tokens() -> None:
    route = respx.post(OPENAI_CHAT).mock(return_value=Response(200, json={
        "model": "gpt-4o-mini",
        "choices": [{"message": {"role": "assistant", "content": "Added."}}],
        "usage": {"prompt_tokens": 31, "completion_tokens": 7},
    }))
    out = OpenAIProvider().chat("sk-openai-key", "gpt-4o-mini", SYSTEM, USER)

    assert out["text"] == "Added." and out["content"] == "Added."
    assert (out["tokens_in"], out["tokens_out"]) == (31, 7)
    assert out["usage"]["total_tokens"] == 38
    assert out["latency_ms"] >= 0

    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer sk-openai-key"
    payload = json.loads(sent.content)
    assert payload["messages"][0] == {"role": "system", "content": SYSTEM}
    assert payload["messages"][1] == {"role": "user", "content": USER}


@respx.mock
def test_openai_list_models_keeps_only_chat_ids() -> None:
    respx.get(OPENAI_MODELS).mock(return_value=Response(200, json={"data": [
        {"id": "gpt-4o-mini"}, {"id": "o3-mini"}, {"id": "chatgpt-4o-latest"},
        {"id": "text-embedding-3-small"}, {"id": "whisper-1"}, {"id": "dall-e-3"},
        {"id": "omni-moderation-latest"}, {"id": "gpt-4o-realtime-preview"},
    ]}))
    ids = [m["id"] for m in OpenAIProvider().list_models("sk-openai-key")]

    assert ids == ["chatgpt-4o-latest", "gpt-4o-mini", "o3-mini"]
    assert all(m["is_free"] is False for m in OpenAIProvider().list_models("k"))


# --- Anthropic ----------------------------------------------------------------


@respx.mock
def test_anthropic_puts_system_at_top_level() -> None:
    """The Messages API rejects a system *role*; it must be its own field."""
    route = respx.post(ANTHROPIC_CHAT).mock(return_value=Response(200, json={
        "model": "claude-sonnet-4-6",
        "content": [{"type": "text", "text": "Added."}],
        "usage": {"input_tokens": 44, "output_tokens": 9},
    }))
    out = AnthropicProvider().chat("sk-ant-key", "claude-sonnet-4-6", SYSTEM, USER)

    assert out["text"] == "Added."
    assert (out["tokens_in"], out["tokens_out"]) == (44, 9)

    sent = route.calls.last.request
    payload = json.loads(sent.content)
    assert payload["system"] == SYSTEM
    assert payload["messages"] == [{"role": "user", "content": USER}]
    assert all(m["role"] != "system" for m in payload["messages"])
    assert payload["max_tokens"] > 0                      # required by the API
    assert sent.headers["x-api-key"] == "sk-ant-key"
    assert sent.headers["anthropic-version"] == "2023-06-01"
    assert "authorization" not in sent.headers


@respx.mock
def test_anthropic_joins_multiple_text_blocks() -> None:
    respx.post(ANTHROPIC_CHAT).mock(return_value=Response(200, json={
        "content": [
            {"type": "text", "text": "One. "},
            {"type": "thinking", "thinking": "ignored"},
            {"type": "text", "text": "Two."},
        ],
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }))
    assert AnthropicProvider().chat("k", "m", SYSTEM, USER)["text"] == "One. Two."


@respx.mock
def test_anthropic_list_models() -> None:
    respx.get(ANTHROPIC_MODELS).mock(return_value=Response(200, json={"data": [
        {"id": "claude-sonnet-4-6", "display_name": "Claude Sonnet 4.6"},
        {"id": "claude-haiku-4-5", "display_name": "Claude Haiku 4.5"},
    ]}))
    models = AnthropicProvider().list_models("sk-ant-key")
    assert [m["id"] for m in models] == ["claude-sonnet-4-6", "claude-haiku-4-5"]
    assert models[0]["name"] == "Claude Sonnet 4.6"
    assert models[0]["is_free"] is False


# --- Gemini -------------------------------------------------------------------


@respx.mock
def test_gemini_chat_uses_contents_and_header_key() -> None:
    route = respx.post(f"{GEMINI_MODELS}/gemini-2.5-flash:generateContent").mock(
        return_value=Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "Added."}]}}],
            "usageMetadata": {"promptTokenCount": 22, "candidatesTokenCount": 5},
            "modelVersion": "gemini-2.5-flash",
        }))
    out = GeminiProvider().chat("gem-key", "gemini-2.5-flash", SYSTEM, USER)

    assert out["text"] == "Added."
    assert (out["tokens_in"], out["tokens_out"]) == (22, 5)

    sent = route.calls.last.request
    payload = json.loads(sent.content)
    assert payload["system_instruction"]["parts"][0]["text"] == SYSTEM
    assert payload["contents"][0]["parts"][0]["text"] == USER
    # the credential travels as a header, never in the URL
    assert sent.headers["x-goog-api-key"] == "gem-key"
    assert "gem-key" not in str(sent.url)


@respx.mock
def test_gemini_list_models_filters_to_generate_content() -> None:
    respx.get(GEMINI_MODELS).mock(return_value=Response(200, json={"models": [
        {"name": "models/gemini-2.5-flash", "displayName": "Gemini 2.5 Flash",
         "inputTokenLimit": 1048576, "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/text-embedding-004", "displayName": "Embedding",
         "supportedGenerationMethods": ["embedContent"]},
    ]}))
    models = GeminiProvider().list_models("gem-key")
    assert [m["id"] for m in models] == ["gemini-2.5-flash"]   # "models/" stripped
    assert models[0]["context_length"] == 1048576


# --- Ollama -------------------------------------------------------------------


@respx.mock
def test_ollama_list_models_from_tags() -> None:
    respx.get(OLLAMA_TAGS).mock(return_value=Response(200, json={
        "models": [{"name": "llama3.2"}, {"name": "qwen2.5:3b"}]}))
    models = OllamaProvider().list_models("")
    assert [m["id"] for m in models] == ["llama3.2", "qwen2.5:3b"]
    assert all(m["is_free"] for m in models)   # local inference costs nothing


@respx.mock
def test_ollama_accepts_a_base_url_override() -> None:
    """The API Keys page stores a base URL in the same per-provider row."""
    route = respx.get("http://192.168.1.9:11434/api/tags").mock(
        return_value=Response(200, json={"models": [{"name": "llama3.2"}]}))
    assert OllamaProvider().list_models("http://192.168.1.9:11434/")
    assert route.called


def test_ollama_ignores_a_non_url_override() -> None:
    """A stray value must not turn into a bogus host."""
    provider = OllamaProvider()
    assert provider._resolve_base("not-a-url") == provider.base_url
    assert provider._resolve_base("") == provider.base_url


@respx.mock
def test_ollama_unreachable_is_actionable() -> None:
    import httpx
    respx.get(OLLAMA_TAGS).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(ProviderUnavailableError, match="ollama serve"):
        OllamaProvider().list_models("")


# --- error normalisation ------------------------------------------------------


@pytest.mark.parametrize("status,body,expected", [
    (401, {"error": {"message": "Incorrect API key"}}, "rejected the API key"),
    (403, {"error": {"message": "Forbidden"}}, "rejected the API key"),
    (429, {"error": {"message": "Rate limit reached"}}, "rate limit reached"),
    (404, {"error": {"message": "The model `nope` does not exist"}}, "does not recognise the model"),
    (500, {"error": {"message": "server melted"}}, "HTTP 500"),
])
@respx.mock
def test_openai_errors_are_user_safe(status: int, body: dict, expected: str) -> None:
    respx.post(OPENAI_CHAT).mock(return_value=Response(status, json=body))
    with pytest.raises(ProviderError) as excinfo:
        OpenAIProvider().chat("sk-openai-secret", "nope", SYSTEM, USER)
    message = str(excinfo.value)
    assert expected.lower() in message.lower()
    assert "sk-openai-secret" not in message          # the key never leaks
    assert "OpenAI" in message                        # names the right provider


@respx.mock
def test_error_redacts_a_key_echoed_by_the_provider() -> None:
    """Some providers quote the offending credential straight back at you."""
    respx.post(ANTHROPIC_CHAT).mock(return_value=Response(
        401, json={"error": {"message": "invalid x-api-key: sk-ant-supersecret-value"}}))
    with pytest.raises(ProviderError) as excinfo:
        AnthropicProvider().chat("sk-ant-supersecret-value", "m", SYSTEM, USER)
    assert "sk-ant-supersecret-value" not in str(excinfo.value)
    assert "***" in str(excinfo.value)


@respx.mock
def test_non_json_error_body_still_produces_a_message() -> None:
    respx.get(OPENAI_MODELS).mock(return_value=Response(502, text="<html>Bad Gateway</html>"))
    with pytest.raises(ProviderError, match="HTTP 502"):
        OpenAIProvider().list_models("sk-openai-key")


# --- custom models pass through unchanged -------------------------------------


@respx.mock
def test_custom_model_id_is_not_whitelisted() -> None:
    """Anything the user types must reach the provider verbatim."""
    route = respx.post(OPENAI_CHAT).mock(return_value=Response(200, json={
        "choices": [{"message": {"content": "ok"}}], "usage": {}}))
    OpenAIProvider().chat("k", "some-unreleased-model-2027", SYSTEM, USER)
    assert json.loads(route.calls.last.request.content)["model"] == "some-unreleased-model-2027"


@respx.mock
def test_unknown_custom_model_surfaces_the_providers_own_words() -> None:
    respx.post(OPENAI_CHAT).mock(return_value=Response(
        404, json={"error": {"message": "The model `typo-4o` does not exist"}}))
    with pytest.raises(ProviderError, match="typo-4o"):
        OpenAIProvider().chat("k", "typo-4o", SYSTEM, USER)


# --- registry -----------------------------------------------------------------


def test_registry_exposes_every_provider() -> None:
    for name, cls in [
        ("openrouter", OpenRouterProvider), ("openai", OpenAIProvider),
        ("anthropic", AnthropicProvider), ("gemini", GeminiProvider),
        ("ollama", OllamaProvider),
    ]:
        provider = get_provider(name)
        assert isinstance(provider, cls)
        assert provider.label


def test_base_urls_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Needed to point a provider at a proxy — or a stub, in the browser tests."""
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
    get_settings.cache_clear()
    assert OpenAIProvider().base_url == "http://127.0.0.1:9999/v1"


# --- gateway routing ----------------------------------------------------------

from collections.abc import Generator                                # noqa: E402

from fastapi.testclient import TestClient                            # noqa: E402
from sqlalchemy import create_engine                                 # noqa: E402
from sqlalchemy.orm import Session, sessionmaker                     # noqa: E402
from sqlalchemy.pool import StaticPool                               # noqa: E402

from app.auth.models import auth_metadata                            # noqa: E402
from app.database import get_db                                      # noqa: E402
from app.llm import gateway as gw                                    # noqa: E402
from app.llm.gateway import llm_metadata, route_model                # noqa: E402
from app.main import app                                             # noqa: E402

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


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    for md in (auth_metadata, llm_metadata):
        md.drop_all(_engine)
        md.create_all(_engine)
    app.dependency_overrides[get_db] = _test_db
    gw.clear_models_cache()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _auth(client: TestClient) -> dict[str, str]:
    client.post("/api/v1/auth/signup", json={"email": "a@example.com", "password": "s3cretpass"})
    token = client.post(
        "/api/v1/auth/login", json={"email": "a@example.com", "password": "s3cretpass"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("model,expected_provider,expected_upstream", [
    ("openai/gpt-4o-mini", "openai", "gpt-4o-mini"),
    ("anthropic/claude-sonnet-4-6", "anthropic", "claude-sonnet-4-6"),
    ("gemini/gemini-2.5-flash", "gemini", "gemini-2.5-flash"),
    ("ollama/llama3.2", "ollama", "llama3.2"),
    ("ollama/qwen2.5:3b", "ollama", "qwen2.5:3b"),
    # a vendor prefix that is not a provider name belongs to OpenRouter, whole
    ("meta-llama/llama-3.3-70b-instruct:free", "openrouter",
     "meta-llama/llama-3.3-70b-instruct:free"),
    ("google/gemma-3-27b-it:free", "openrouter", "google/gemma-3-27b-it:free"),
    ("some-bare-model", "openrouter", "some-bare-model"),
    # explicit escape hatch for an OpenRouter id that looks namespaced
    ("openrouter/openai/gpt-4o-mini", "openrouter", "openai/gpt-4o-mini"),
])
def test_prefix_routing(model: str, expected_provider: str, expected_upstream: str) -> None:
    assert route_model(model) == (expected_provider, expected_upstream)


def test_demo_bypasses_routing() -> None:
    assert route_model("anything/at/all", "demo") == ("demo", "anything/at/all")


@pytest.mark.parametrize("model,provider_name", [
    ("openai/gpt-4o-mini", "OpenAI"),
    ("anthropic/claude-sonnet-4-6", "Anthropic"),
    ("gemini/gemini-2.5-flash", "Gemini"),
    ("meta-llama/llama-3.3-70b-instruct:free", "OpenRouter"),
])
def test_each_provider_requires_its_own_key(
    client: TestClient, model: str, provider_name: str
) -> None:
    """A key for one provider must not authorise a call to another."""
    db = _TestSession()
    try:
        with pytest.raises(LookupError, match=provider_name):
            gw.chat(db, user_id=4242, model=model, system_context="s", user_message="u")
    finally:
        db.close()


@respx.mock
def test_ollama_is_exempt_from_the_key_requirement(client: TestClient) -> None:
    respx.post(OLLAMA_CHAT).mock(return_value=Response(200, json={
        "model": "llama3.2", "message": {"content": "local reply"},
        "prompt_eval_count": 11, "eval_count": 3,
    }))
    db = _TestSession()
    try:
        out = gw.chat(db, user_id=4242, model="ollama/llama3.2",
                      system_context="s", user_message="u")
    finally:
        db.close()
    assert out["provider"] == "ollama" and out["text"] == "local reply"
    assert json.loads(respx.calls.last.request.content)["model"] == "llama3.2"


@respx.mock
def test_key_saved_for_one_provider_routes_to_that_provider(client: TestClient) -> None:
    headers = _auth(client)
    client.post("/api/v1/keys/provider",
                json={"provider": "anthropic", "api_key": "sk-ant-routed-key"}, headers=headers)
    route = respx.post(ANTHROPIC_CHAT).mock(return_value=Response(200, json={
        "content": [{"type": "text", "text": "hi"}],
        "usage": {"input_tokens": 5, "output_tokens": 2},
    }))
    db = _TestSession()
    try:
        out = gw.chat(db, user_id=1, model="anthropic/claude-sonnet-4-6",
                      system_context="s", user_message="u")
    finally:
        db.close()
    assert out["provider"] == "anthropic"          # what the audit log records
    assert route.calls.last.request.headers["x-api-key"] == "sk-ant-routed-key"
    # the namespace is stripped before the id goes upstream
    assert json.loads(route.calls.last.request.content)["model"] == "claude-sonnet-4-6"


@respx.mock
def test_custom_model_reaches_the_provider_unchanged(client: TestClient) -> None:
    """No whitelist anywhere on the path: typed id in, typed id out."""
    headers = _auth(client)
    client.post("/api/v1/keys/provider",
                json={"provider": "openai", "api_key": "sk-openai-custom"}, headers=headers)
    route = respx.post(OPENAI_CHAT).mock(return_value=Response(200, json={
        "choices": [{"message": {"content": "ok"}}], "usage": {}}))
    db = _TestSession()
    try:
        gw.chat(db, user_id=1, model="openai/ft:gpt-4o-mini:acme:custom:abc123",
                system_context="s", user_message="u")
    finally:
        db.close()
    assert json.loads(route.calls.last.request.content)["model"] == (
        "ft:gpt-4o-mini:acme:custom:abc123")


@respx.mock
def test_chat_route_audits_the_routed_provider(client: TestClient) -> None:
    """The audit row must name who actually served it, not who was asked."""
    from app.memory.audit import audit_metadata
    from app.memory.storage import metadata as storage_metadata
    for md in (storage_metadata, audit_metadata):
        md.drop_all(_engine)
        md.create_all(_engine)

    headers = _auth(client)
    client.post("/api/v1/keys/provider",
                json={"provider": "gemini", "api_key": "gem-audit-key"}, headers=headers)
    client.post("/api/v1/memory/ingest",
                json={"session_tag": "s1", "text": "Stack: React + Tailwind."}, headers=headers)
    respx.post(f"{GEMINI_MODELS}/gemini-2.5-flash:generateContent").mock(
        return_value=Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "done"}]}}],
            "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 1},
        }))

    resp = client.post("/api/v1/chat", json={
        "session_tag": "s1", "query": "Now add a pricing section.",
        "model": "gemini/gemini-2.5-flash",
    }, headers=headers)
    assert resp.status_code == 200, resp.text

    trail = client.get("/api/v1/audit", headers=headers).json()["entries"]
    assert trail[0]["provider"] == "gemini"
    assert trail[0]["model"] == "gemini-2.5-flash"


@respx.mock
def test_provider_error_reaches_the_client_without_the_key(client: TestClient) -> None:
    from app.memory.audit import audit_metadata
    from app.memory.storage import metadata as storage_metadata
    for md in (storage_metadata, audit_metadata):
        md.drop_all(_engine)
        md.create_all(_engine)

    headers = _auth(client)
    client.post("/api/v1/keys/provider",
                json={"provider": "openai", "api_key": "sk-openai-leakcheck"}, headers=headers)
    client.post("/api/v1/memory/ingest",
                json={"session_tag": "s1", "text": "Stack: React + Tailwind."}, headers=headers)
    respx.post(OPENAI_CHAT).mock(return_value=Response(
        401, json={"error": {"message": "bad key sk-openai-leakcheck"}}))

    resp = client.post("/api/v1/chat", json={
        "session_tag": "s1", "query": "hello", "model": "openai/gpt-4o-mini",
    }, headers=headers)
    assert resp.status_code == 502
    assert "sk-openai-leakcheck" not in resp.text
    assert "rejected the API key" in resp.json()["detail"]


@respx.mock
def test_openrouter_ids_that_look_namespaced_are_qualified(client: TestClient) -> None:
    """"anthropic/claude-…" is a real OpenRouter id; bare, it would route to
    Anthropic and demand a key the user never needed."""
    headers = _auth(client)
    client.post("/api/v1/keys/provider",
                json={"provider": "openrouter", "api_key": "sk-or-v1-testkey1234"},
                headers=headers)
    respx.get("https://openrouter.ai/api/v1/models").mock(return_value=Response(200, json={
        "data": [{"id": "meta-llama/llama-3.3-70b-instruct:free", "context_length": 128000,
                  "pricing": {"prompt": "0", "completion": "0"},
                  "architecture": {"output_modalities": ["text"]}}]}))

    group = client.get("/api/v1/models", headers=headers).json()["groups"][0]
    ids = [m["id"] for m in group["free"] + group["paid"]]

    # a plain vendor prefix is left alone...
    assert "meta-llama/llama-3.3-70b-instruct:free" in ids
    # ...but a provider-named one is qualified
    assert "openrouter/anthropic/claude-sonnet-4.6" in ids
    assert "anthropic/claude-sonnet-4.6" not in ids
    assert "openai/gpt-4o-mini" not in ids
    # and every id in this group still routes back to OpenRouter
    for model_id in ids:
        assert route_model(model_id)[0] == "openrouter"
