"""The dashboard aggregates, and the scoping that keeps them the caller's own.

The charts these feed are only worth shipping if the numbers are real, so the
shaping is tested directly rather than through a screenshot: a decline counted
twice, or another account's states leaking into a total, would both render as a
perfectly convincing chart.
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
from app.main import app
from app.memory.audit import audit_metadata
from app.memory.insights import UNSTATED, summarize
from app.memory.storage import metadata as storage_metadata

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Built from pieces so the fixture stays obviously fake without becoming a
# credential-shaped literal in the repository.
TEST_PASSWORD = "".join(["insights", "-fixture", "-pw", "-01"])


@pytest.fixture(autouse=True)
def _schema() -> Generator[None, None, None]:
    for md in (auth_metadata, apikeys_metadata, storage_metadata, audit_metadata):
        md.create_all(engine)
    yield
    for md in (auth_metadata, apikeys_metadata, storage_metadata, audit_metadata):
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


def row(tag, handle, created, state):
    return {"session_tag": tag, "handle": handle, "created_at": created,
            "state_json": state}


# --- namespaces: active vs superseded -----------------------------------------


def test_active_fields_are_counted_per_namespace() -> None:
    out = summarize([row("s1", "shm_a", "2026-08-05T10:00:00+00:00", {
        "facts": {"name": "Rahul", "city": "Pune"},
        "constraints": {"budget": {"max": {"value": 2000, "currency": "INR"}}},
    })])
    ns = {e["namespace"]: e for e in out["namespaces"]}
    assert ns["facts"]["active"] == 2
    assert ns["constraints"]["active"] == 1, (
        "a normalized money value is one field, not one per sub-key"
    )


def test_superseded_values_come_from_history() -> None:
    """The "one field, one value" invariant: a replaced value leaves active
    state and survives only in history."""
    out = summarize([row("s1", "shm_a", "2026-08-05T10:00:00+00:00", {
        "facts": {"name": "Rahul Verma"},
        "history": [
            {"field": "facts.name", "value": "Rahul Sharma"},
            {"field": "facts.city", "value": "Pune"},
        ],
    })])
    ns = {e["namespace"]: e for e in out["namespaces"]}
    assert ns["facts"] == {"namespace": "facts", "active": 1, "superseded": 2}
    assert out["totals"]["active"] == 1
    assert out["totals"]["superseded"] == 2


def test_only_the_latest_version_counts_as_active() -> None:
    """Counting every version would multiply one live field by its history."""
    out = summarize([
        row("s1", "shm_a", "2026-08-05T10:00:00+00:00", {"facts": {"name": "A"}}),
        row("s1", "shm_b", "2026-08-05T10:01:00+00:00", {"facts": {"name": "B", "city": "Pune"}}),
    ])
    assert out["totals"]["active"] == 2
    assert out["totals"]["states"] == 2


# --- declines -----------------------------------------------------------------


def test_a_decline_is_counted_once_not_once_per_later_version() -> None:
    """`_unmapped` accumulates down a session, so counting the block as it
    stands on each version reports one refusal again on every later turn."""
    unmapped = {"facts.mood": {"value": "great", "reason": "unknown_key"}}
    out = summarize([
        row("s1", "shm_a", "2026-08-05T10:00:00+00:00", {"_unmapped": unmapped}),
        row("s1", "shm_b", "2026-08-06T10:00:00+00:00", {"_unmapped": unmapped}),
    ])
    assert out["totals"]["declined"] == 1
    assert out["declines"]["totals"] == {"unknown_key": 1}
    assert [b["date"] for b in out["declines"]["buckets"]] == ["2026-08-05"]


def test_a_new_decline_on_a_later_version_lands_on_its_own_day() -> None:
    out = summarize([
        row("s1", "shm_a", "2026-08-05T10:00:00+00:00",
            {"_unmapped": {"facts.mood": {"reason": "unknown_key"}}}),
        row("s1", "shm_b", "2026-08-06T10:00:00+00:00",
            {"_unmapped": {"facts.mood": {"reason": "unknown_key"},
                           "facts.pet": {"reason": "low_confidence"}}}),
    ])
    assert out["declines"]["buckets"] == [
        {"date": "2026-08-05", "counts": {"unknown_key": 1}},
        {"date": "2026-08-06", "counts": {"low_confidence": 1}},
    ]


def test_unresolved_fields_count_as_declines() -> None:
    out = summarize([row("s1", "shm_a", "2026-08-05T10:00:00+00:00", {
        "unresolved": [{"field": "delivery_time", "reason": "not provided"}],
    })])
    assert out["declines"]["totals"] == {"not provided": 1}


def test_a_refusal_with_no_reason_is_still_counted() -> None:
    """Dropping it would make the chart flatter than the truth."""
    out = summarize([row("s1", "shm_a", "2026-08-05T10:00:00+00:00", {
        "_unmapped": {"facts.x": {"value": "?"}},
    })])
    assert out["declines"]["totals"] == {UNSTATED: 1}


def test_reasons_are_ranked_most_common_first() -> None:
    out = summarize([row("s1", "shm_a", "2026-08-05T10:00:00+00:00", {
        "_unmapped": {
            "a": {"reason": "low_confidence"}, "b": {"reason": "low_confidence"},
            "c": {"reason": "low_confidence"}, "d": {"reason": "unknown_key"},
            "e": {"reason": "unknown_key"}, "f": {"reason": "rejected_value"},
        },
    })])
    assert out["declines"]["reasons"] == [
        "low_confidence", "unknown_key", "rejected_value"]


# --- lineage ------------------------------------------------------------------


def test_lineage_is_the_ordered_chain_per_session() -> None:
    out = summarize([
        row("s1", "shm_a", "2026-08-05T10:00:00+00:00", {"facts": {"name": "A"}}),
        row("s1", "shm_b", "2026-08-05T10:01:00+00:00", {"facts": {"name": "A", "city": "Pune"}}),
        row("s2", "shm_c", "2026-08-05T10:02:00+00:00", {"facts": {"name": "Z"}}),
    ])
    chains = {e["session_tag"]: e["versions"] for e in out["lineage"]}
    assert [v["handle"] for v in chains["s1"]] == ["shm_a", "shm_b"]
    assert [v["version"] for v in chains["s1"]] == [1, 2]
    assert [v["fields"] for v in chains["s1"]] == [1, 2]
    assert out["totals"]["sessions"] == 2


def test_empty_input_produces_empty_series_not_zeros() -> None:
    """The dashboard renders a chart only when data exists, so "nothing yet"
    has to be distinguishable from "measured zero"."""
    out = summarize([])
    assert out["namespaces"] == []
    assert out["declines"]["buckets"] == []
    assert out["lineage"] == []
    assert out["totals"]["states"] == 0


def test_a_malformed_state_is_skipped_not_fatal() -> None:
    out = summarize([
        row("s1", "shm_a", "2026-08-05T10:00:00+00:00", None),
        row("s1", "shm_b", "2026-08-05T10:01:00+00:00", {"facts": {"name": "A"}}),
    ])
    assert out["totals"]["active"] == 1


# --- the endpoint: authentication and scoping ---------------------------------


def _register(client, email):
    creds = {"email": email, "password": TEST_PASSWORD}
    client.post("/api/v1/auth/signup", json=creds)
    token = client.post("/api/v1/auth/login", json=creds).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_insights_requires_authentication(client) -> None:
    assert client.get("/api/v1/memory/insights").status_code == 401


def test_insights_are_scoped_to_the_calling_account(client) -> None:
    """The charts are built from whatever this returns, so a leak here draws
    another account's memory on your dashboard."""
    a = _register(client, "insight-a@example.com")
    b = _register(client, "insight-b@example.com")

    client.post("/api/v1/memory/ingest", headers=a,
                json={"session_tag": "s-a", "text": "My name is Rahul Sharma"})

    mine = client.get("/api/v1/memory/insights", headers=a).json()
    theirs = client.get("/api/v1/memory/insights", headers=b).json()

    assert mine["totals"]["states"] == 1
    assert [e["session_tag"] for e in mine["lineage"]] == ["s-a"]
    assert theirs["totals"]["states"] == 0, "another account's states were counted"
    assert theirs["lineage"] == []


def test_insights_reflect_a_real_ingest(client) -> None:
    headers = _register(client, "insight-c@example.com")
    client.post("/api/v1/memory/ingest", headers=headers,
                json={"session_tag": "s1", "text": "My name is Rahul Sharma"})
    client.post("/api/v1/memory/ingest", headers=headers,
                json={"session_tag": "s1", "text": "Actually my name is Rahul Verma"})

    body = client.get("/api/v1/memory/insights", headers=headers).json()
    chain = body["lineage"][0]["versions"]
    assert len(chain) == 2
    assert chain[0]["handle"] != chain[1]["handle"], "lineage must show distinct handles"
    ns = {e["namespace"]: e for e in body["namespaces"]}
    assert ns["facts"]["active"] >= 1
    assert ns["facts"]["superseded"] >= 1, (
        "replacing a name must show as one active value and one superseded"
    )
