"""End-to-end integration test for the full StateJar pipeline.

ingest → version → query → chat (mocked OpenRouter) → audit,
verifying minimal disclosure and that no raw transcript reaches the LLM.
"""

import json
from collections.abc import Generator

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tests.conftest import fake_key
from app.auth.models import auth_metadata
from app.config import get_settings
from app.database import get_db
from app.llm.gateway import llm_metadata
from app.llm.providers import OpenRouterProvider
from app.main import app
from app.memory.audit import audit_metadata
from app.memory.storage import metadata as storage_metadata

_engine = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
_TestSession = sessionmaker(bind=_engine)

INGEST_TEXT = (
    "My name is Ayaan. I prefer emails, not calls. "
    "Budget is under ₹2000. I haven't decided the delivery time."
)


def _test_db() -> Generator[Session, None, None]:
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    for md in (auth_metadata, storage_metadata, audit_metadata, llm_metadata):
        md.drop_all(_engine)
        md.create_all(_engine)
    app.dependency_overrides[get_db] = _test_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def headers(client: TestClient) -> dict[str, str]:
    client.post("/api/v1/auth/signup", json={"email": "a@example.com", "password": "s3cretpass"})
    token = client.post(
        "/api/v1/auth/login", json={"email": "a@example.com", "password": "s3cretpass"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_all_routes_require_jwt(client: TestClient) -> None:
    assert client.post("/api/v1/memory/ingest", json={"session_tag": "s", "text": "x"}).status_code == 401
    assert client.post("/api/v1/memory/query", json={"session_tag": "s", "query": "x"}).status_code == 401
    assert client.post("/api/v1/chat", json={"session_tag": "s", "query": "x"}).status_code == 401
    assert client.get("/api/v1/memory/versions?session_tag=s").status_code == 401
    assert client.get("/api/v1/audit").status_code == 401


@respx.mock
def test_full_pipeline_end_to_end(
    client: TestClient, headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 1. ingest session 1
    r = client.post(
        "/api/v1/memory/ingest",
        json={"session_tag": "session-1", "text": INGEST_TEXT},
        headers=headers,
    )
    assert r.status_code == 200
    ingest1 = r.json()
    h1 = ingest1["handle"]
    assert h1.startswith("shm_")
    assert ingest1["parent_handle"] is None
    assert ingest1["state"]["facts"]["name"] == "Ayaan"
    assert ingest1["state"]["preferences"]["contact_mode"] == "email"
    assert ingest1["state"]["constraints"]["budget"]["max"]["value"] == 2000

    # 2. second ingest evolves state (budget change → conflict, new handle)
    r = client.post(
        "/api/v1/memory/ingest",
        json={"session_tag": "session-1", "text": "Actually my budget is max ₹2500."},
        headers=headers,
    )
    ingest2 = r.json()
    h2 = ingest2["handle"]
    assert h2 != h1
    assert ingest2["parent_handle"] == h1
    assert ingest2["state"]["constraints"]["budget"]["max"]["value"] == 2500
    assert any(c["field"] == "constraints.budget.max" for c in ingest2["conflicts"])

    # 3. version chain intact, old state retrievable
    versions = client.get(
        "/api/v1/memory/versions?session_tag=session-1", headers=headers
    ).json()["versions"]
    assert versions == [h1, h2]

    # 4. query returns the right subset, and never the superseded value
    #
    # With the shipped default a state this small is returned whole: selecting
    # from a few hundred tokens saves nothing worth being wrong for. What must
    # hold either way is that the *stale* budget never reaches the caller — the
    # conflict record holds it, and conflicts are audit-only.
    q = client.post(
        "/api/v1/memory/query",
        json={"session_tag": "session-1", "query": "Book my delivery"},
        headers=headers,
    ).json()
    assert q["handle_used"] == h2
    assert q["subset"]["preferences"]["contact_mode"] == "email"
    assert q["subset"]["constraints"]["budget"] == {
        "max": {"value": 2500, "currency": "INR"}
    }
    assert q["metadata"]["retrieval_mode"] == "full_state"
    assert "conflicts" not in q["subset"]
    assert "2000" not in json.dumps(q["subset"])   # the superseded figure

    # and with the size fallback off, selection still narrows to the intent
    get_settings.cache_clear()
    monkeypatch.setenv("RETRIEVER_FULL_STATE_TOKENS", "0")
    try:
        narrow = client.post(
            "/api/v1/memory/query",
            json={"session_tag": "session-1", "query": "Book my delivery"},
            headers=headers,
        ).json()
        assert narrow["metadata"]["retrieval_mode"] == "intent_map"
        assert "facts" not in narrow["subset"]   # name not needed to book
    finally:
        monkeypatch.delenv("RETRIEVER_FULL_STATE_TOKENS", raising=False)
        get_settings.cache_clear()

    # 5. save provider key + chat (mocked OpenRouter, cross-session: new "session")
    client.post(
        "/api/v1/keys/provider",
        json={"provider": "openrouter", "api_key": fake_key("or-9999")},
        headers=headers,
    )
    route = respx.post(OpenRouterProvider.BASE_URL).mock(
        return_value=Response(
            200,
            json={
                "model": "openai/gpt-4o-mini",
                "choices": [{"message": {"role": "assistant",
                                         "content": "Booked! I'll email you within budget."}}],
                "usage": {"total_tokens": 30},
            },
        )
    )
    chat = client.post(
        "/api/v1/chat",
        json={"session_tag": "session-1", "query": "Book my delivery with my usual preferences"},
        headers=headers,
    )
    assert chat.status_code == 200
    chat_body = chat.json()
    assert chat_body["response"].startswith("Booked!")
    assert chat_body["handle_used"] == h2
    assert set(chat_body["subset_keys"]) >= {
        "preferences.contact_mode", "constraints.budget.max",
    }

    # 6. LLM received ONLY the subset — never the raw transcript
    sent = json.loads(route.calls.last.request.content)
    system_msg = next(m["content"] for m in sent["messages"] if m["role"] == "system")
    assert f"StateJar handle {h2}" in system_msg
    assert "contact_mode" in system_msg
    assert INGEST_TEXT not in json.dumps(sent)          # no full transcript
    assert "My name is Ayaan" not in json.dumps(sent)   # no raw text fragments
    # The name IS disclosed here, and should be: the query said "my usual
    # preferences", which is a request for what StateJar has on file. What
    # must never appear is the sentence the user typed to establish it — the
    # claim is no chat replay, not no facts.
    assert '"name": "Ayaan"' in system_msg

    # The superseded ₹2000 appears exactly once, inside the change block, and
    # labelled as prior. That distinction is the whole of P0-4: disclosing the
    # conflicts array hands a model a stale value as if it were current, while
    # "was 2000, now 2500" is what lets it say "updated" instead of the
    # "already set to 2500 — nothing to change" it used to answer.
    state_part, _, changed_part = system_msg.partition("CHANGED BY THE USER'S")
    assert "2000" not in state_part, "stale value must not read as current"
    assert "was INR 2000, now INR 2500" in changed_part

    # 7. audit row exists and matches
    trail = client.get("/api/v1/audit", headers=headers).json()["entries"]
    assert len(trail) == 1
    entry = trail[0]
    assert entry["request_id"] == chat_body["audit_id"]
    assert entry["handle_used"] == h2
    assert entry["provider"] == "openrouter"
    assert entry["session_tag"] == "session-1"
    assert set(entry["subset_keys"]) == set(chat_body["subset_keys"])

    # 8. audit trail filters by session_tag
    same = client.get(
        "/api/v1/audit?session_tag=session-1", headers=headers
    ).json()["entries"]
    assert [e["request_id"] for e in same] == [entry["request_id"]]
    other = client.get(
        "/api/v1/audit?session_tag=session-2", headers=headers
    ).json()["entries"]
    assert other == []


def test_query_without_state_is_404(client: TestClient, headers: dict[str, str]) -> None:
    r = client.post(
        "/api/v1/memory/query",
        json={"session_tag": "empty", "query": "book"},
        headers=headers,
    )
    assert r.status_code == 404


def test_chat_without_provider_key_is_400(client: TestClient, headers: dict[str, str]) -> None:
    client.post(
        "/api/v1/memory/ingest",
        json={"session_tag": "s2", "text": INGEST_TEXT},
        headers=headers,
    )
    r = client.post(
        "/api/v1/chat", json={"session_tag": "s2", "query": "Book it"}, headers=headers
    )
    assert r.status_code == 400
    assert "API key" in r.json()["detail"]


@respx.mock
def test_chat_upstream_5xx_is_502(client: TestClient, headers: dict[str, str]) -> None:
    client.post(
        "/api/v1/memory/ingest",
        json={"session_tag": "s3", "text": INGEST_TEXT},
        headers=headers,
    )
    client.post(
        "/api/v1/keys/provider",
        json={"provider": "openrouter", "api_key": fake_key("or-0000")},
        headers=headers,
    )
    respx.post(OpenRouterProvider.BASE_URL).mock(
        return_value=Response(500, json={"error": {"message": "upstream exploded"}})
    )
    r = client.post(
        "/api/v1/chat", json={"session_tag": "s3", "query": "Book it"}, headers=headers
    )
    assert r.status_code == 502
    # the provider's own words, prefixed with who said them
    detail = r.json()["detail"]
    assert "upstream exploded" in detail and "OpenRouter" in detail


@respx.mock
def test_chat_upstream_timeout_is_502(client: TestClient, headers: dict[str, str]) -> None:
    import httpx

    client.post(
        "/api/v1/memory/ingest",
        json={"session_tag": "s4", "text": INGEST_TEXT},
        headers=headers,
    )
    client.post(
        "/api/v1/keys/provider",
        json={"provider": "openrouter", "api_key": fake_key("or-0001")},
        headers=headers,
    )
    respx.post(OpenRouterProvider.BASE_URL).mock(
        side_effect=httpx.ConnectTimeout("boom")
    )
    r = client.post(
        "/api/v1/chat", json={"session_tag": "s4", "query": "Book it"}, headers=headers
    )
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert "OpenRouter" in detail and "timed out" in detail


def test_demo_chat_needs_no_key_and_writes_audit(
    client: TestClient, headers: dict[str, str]
) -> None:
    client.post(
        "/api/v1/memory/ingest",
        json={"session_tag": "demo-1", "text": INGEST_TEXT},
        headers=headers,
    )
    r = client.post(
        "/api/v1/chat",
        json={
            "session_tag": "demo-1",
            "query": "Now add a pricing section.",
            "provider": "demo",
            "model": "scripted-demo",
        },
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert "Pricing section" in body["response"]
    trail = client.get(
        "/api/v1/audit?session_tag=demo-1", headers=headers
    ).json()["entries"]
    assert len(trail) == 1
    assert trail[0]["provider"] == "demo"
    assert trail[0]["model"] == "scripted-demo"


def test_audited_query_needs_no_key_and_writes_audit(
    client: TestClient, headers: dict[str, str]
) -> None:
    """The instant demo's whole backend surface: ingest + audited query only."""
    client.post(
        "/api/v1/memory/ingest",
        json={"session_tag": "demo-2", "text": INGEST_TEXT},
        headers=headers,
    )
    r = client.post(
        "/api/v1/memory/query",
        json={
            "session_tag": "demo-2",
            "query": "Book my delivery with my usual preferences",
            "audit": True,
        },
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["audit_id"]
    assert body["metadata"]["subset_keys"]
    trail = client.get(
        "/api/v1/audit?session_tag=demo-2", headers=headers
    ).json()["entries"]
    assert len(trail) == 1
    assert trail[0]["request_id"] == body["audit_id"]
    assert trail[0]["provider"] == "demo"
    assert trail[0]["subset_keys"] == body["metadata"]["subset_keys"]


def test_plain_query_writes_no_audit(client: TestClient, headers: dict[str, str]) -> None:
    client.post(
        "/api/v1/memory/ingest",
        json={"session_tag": "demo-3", "text": INGEST_TEXT},
        headers=headers,
    )
    r = client.post(
        "/api/v1/memory/query",
        json={"session_tag": "demo-3", "query": "What's the budget?"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["audit_id"] is None
    trail = client.get(
        "/api/v1/audit?session_tag=demo-3", headers=headers
    ).json()["entries"]
    assert trail == []
