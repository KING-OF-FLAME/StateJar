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

from app.auth.models import auth_metadata
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
def test_full_pipeline_end_to_end(client: TestClient, headers: dict[str, str]) -> None:
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
    assert ingest1["state"]["constraints"]["budget_inr_max"] == 2000

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
    assert ingest2["state"]["constraints"]["budget_inr_max"] == 2500
    assert any(c["field"] == "constraints.budget_inr_max" for c in ingest2["conflicts"])

    # 3. version chain intact, old state retrievable
    versions = client.get(
        "/api/v1/memory/versions?session_tag=session-1", headers=headers
    ).json()["versions"]
    assert versions == [h1, h2]

    # 4. query returns minimal subset only
    q = client.post(
        "/api/v1/memory/query",
        json={"session_tag": "session-1", "query": "Book my delivery"},
        headers=headers,
    ).json()
    assert q["handle_used"] == h2
    assert q["subset"]["preferences"] == {"contact_mode": "email"}
    assert q["subset"]["constraints"] == {"budget_inr_max": 2500}
    assert "facts" not in q["subset"]  # name not disclosed for a booking query

    # 5. save provider key + chat (mocked OpenRouter, cross-session: new "session")
    client.post(
        "/api/v1/keys/provider",
        json={"provider": "openrouter", "api_key": "sk-or-v1-testkey9999"},
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
        "preferences.contact_mode", "constraints.budget_inr_max",
    }

    # 6. LLM received ONLY the subset — never the raw transcript
    sent = json.loads(route.calls.last.request.content)
    system_msg = next(m["content"] for m in sent["messages"] if m["role"] == "system")
    assert f"StateJar handle {h2}" in system_msg
    assert "contact_mode" in system_msg
    assert INGEST_TEXT not in json.dumps(sent)          # no full transcript
    assert "My name is Ayaan" not in json.dumps(sent)   # no raw text fragments
    assert "Ayaan" not in system_msg                    # facts not in booking subset

    # 7. audit row exists and matches
    trail = client.get("/api/v1/audit", headers=headers).json()["entries"]
    assert len(trail) == 1
    entry = trail[0]
    assert entry["request_id"] == chat_body["audit_id"]
    assert entry["handle_used"] == h2
    assert entry["provider"] == "openrouter"
    assert set(entry["subset_keys"]) == set(chat_body["subset_keys"])


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
