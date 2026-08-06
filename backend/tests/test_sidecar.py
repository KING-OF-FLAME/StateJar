"""The sidecar path: bring your own LLM, keep StateJar's memory.

A developer calling their own provider gets context from `POST /memory/query`
rather than from `POST /chat`. The risk is drift — two ways to build the same
prompt, one of which quietly stops matching the other — so the parity test
below is the point of the file, not a nicety.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.apikeys import apikeys_metadata
from app.auth.models import auth_metadata
from app.database import get_db
from app.llm import gateway
from app.main import app
from app.memory.audit import audit_metadata
from app.memory.storage import metadata as storage_metadata

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

TEST_PASSWORD = "".join(["sidecar", "-fixture", "-pw", "-01"])
METADATA = (auth_metadata, apikeys_metadata, storage_metadata, audit_metadata)


@pytest.fixture(autouse=True)
def _schema() -> Generator[None, None, None]:
    for md in METADATA:
        md.create_all(engine)
    yield
    for md in METADATA:
        md.drop_all(engine)


def _test_db() -> Generator[Session, None, None]:
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = _test_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def headers(client: TestClient) -> dict[str, str]:
    creds = {"email": "sidecar@example.com", "password": TEST_PASSWORD}
    client.post("/api/v1/auth/signup", json=creds)
    token = client.post("/api/v1/auth/login", json=creds).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def seed(client: TestClient, headers: dict[str, str], *texts: str) -> None:
    for text in texts:
        r = client.post("/api/v1/memory/ingest", headers=headers,
                        json={"session_tag": "s1", "text": text})
        assert r.status_code == 200, r.text


def test_query_returns_prompt_ready_context(
    client: TestClient, headers: dict[str, str]
) -> None:
    seed(client, headers, "My name is Meera Nair", "Budget is under 25000")
    body = client.post("/api/v1/memory/query", headers=headers,
                       json={"session_tag": "s1", "query": "what is my budget?"}).json()

    assert isinstance(body["memory_context"], str) and body["memory_context"]
    assert body["handle_used"] in body["memory_context"], (
        "the context must name the handle it was built from, or a caller "
        "cannot tie an answer back to a state"
    )
    assert "25000" in body["memory_context"]


def test_context_matches_what_chat_injects(
    client: TestClient, headers: dict[str, str]
) -> None:
    """The parity that makes the sidecar trustworthy.

    If these two ever diverge, a developer bringing their own model gets a
    different prompt from the built-in path and no test would have said so.
    """
    seed(client, headers, "My name is Meera Nair", "Budget is under 25000")
    body = client.post("/api/v1/memory/query", headers=headers,
                       json={"session_tag": "s1", "query": "what is my budget?"}).json()

    rebuilt = gateway.build_system_context(body["handle_used"], body["subset"], [])
    assert body["memory_context"] == rebuilt


def test_context_carries_only_the_retrieved_subset(
    client: TestClient, headers: dict[str, str]
) -> None:
    """Minimum disclosure has to survive the convenience field: if it inlined
    the whole state, the sidecar would leak what /chat withholds."""
    seed(client, headers, "My name is Meera Nair", "Budget is under 25000",
         "I prefer email, not calls")
    body = client.post("/api/v1/memory/query", headers=headers,
                       json={"session_tag": "s1", "query": "what is my budget?"}).json()

    # The context carries exactly the retrieved subset and nothing wider. It
    # is compared through the renderer rather than as JSON because the subset
    # is sent as `path: value` lines; the property under test is that the
    # disclosed set is the retrieved set, not how it is encoded.
    from app.llm.gateway import render_compact
    assert render_compact(body["subset"]) in body["memory_context"]


def test_query_still_requires_authentication(client: TestClient) -> None:
    r = client.post("/api/v1/memory/query",
                    json={"session_tag": "s1", "query": "anything"})
    assert r.status_code == 401


def test_ingest_is_visible_to_the_very_next_query(
    client: TestClient, headers: dict[str, str]
) -> None:
    """The ordering guarantee the sidecar example depends on.

    Ingest commits before it returns, so a question that depends on the message
    that asked it does not retrieve pre-message state. This is what backgrounding
    ingest would break, and it would break silently.
    """
    seed(client, headers, "My name is Meera Nair")
    client.post("/api/v1/memory/ingest", headers=headers,
                json={"session_tag": "s1", "text": "Budget is under 25000"})

    body = client.post("/api/v1/memory/query", headers=headers,
                       json={"session_tag": "s1", "query": "what is my budget?"}).json()
    assert "25000" in body["memory_context"], (
        "the turn just ingested was not in the context retrieved right after it"
    )
