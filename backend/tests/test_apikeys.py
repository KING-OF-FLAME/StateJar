"""Tests for developer API keys: issue, authenticate, revoke, scope."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.apikeys import KEY_PREFIX, api_keys, apikeys_metadata, generate_key, hash_key
from app.auth.models import auth_metadata
from app.database import get_db
from app.llm.gateway import llm_metadata
from app.main import app
from app.memory.audit import audit_metadata
from app.memory.storage import metadata as storage_metadata

GENERATE = "/api/v1/apikeys/generate"
LIST = "/api/v1/apikeys"
INGEST = "/api/v1/memory/ingest"
QUERY = "/api/v1/memory/query"
USAGE = "/api/v1/usage"
PROVIDER_KEYS = "/api/v1/keys/provider"

PASSWORD = "s3cretpass"
TEXT = "My name is Ayaan, budget under ₹2000. I prefer email."

_engine = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
_TestSession = sessionmaker(bind=_engine)

_ALL_METADATA = (
    auth_metadata, llm_metadata, storage_metadata, audit_metadata, apikeys_metadata,
)


def _test_db() -> Generator[Session, None, None]:
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def client() -> Generator[TestClient, None, None]:
    for md in _ALL_METADATA:
        md.drop_all(_engine)
        md.create_all(_engine)
    app.dependency_overrides[get_db] = _test_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _jwt_headers(client: TestClient, email: str = "dev@example.com") -> dict[str, str]:
    client.post("/api/v1/auth/signup", json={"email": email, "password": PASSWORD})
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _new_key(client: TestClient, headers: dict[str, str]) -> tuple[int, str]:
    body = client.post(GENERATE, headers=headers).json()
    return body["id"], body["api_key"]


# --- issuing ------------------------------------------------------------------


def test_generated_key_has_the_documented_shape() -> None:
    key = generate_key()
    assert key.startswith(KEY_PREFIX)
    assert len(key) > len(KEY_PREFIX) + 32
    assert generate_key() != generate_key()  # not a fixed or seeded value


def test_generate_returns_the_key_once(client: TestClient) -> None:
    headers = _jwt_headers(client)
    resp = client.post(GENERATE, headers=headers)
    assert resp.status_code == 201

    body = resp.json()
    key = body["api_key"]
    assert key.startswith(KEY_PREFIX)
    assert body["key_last4"] == key[-4:]

    # the listing never shows it again
    listed = client.get(LIST, headers=headers).json()
    assert len(listed) == 1
    assert listed[0]["id"] == body["id"]
    assert listed[0]["key_last4"] == key[-4:]
    assert key not in client.get(LIST, headers=headers).text


def test_only_the_hash_is_stored(client: TestClient) -> None:
    """A database leak must not yield working credentials."""
    _, key = _new_key(client, _jwt_headers(client))

    db = _TestSession()
    try:
        rows = db.execute(select(api_keys)).mappings().all()
    finally:
        db.close()

    assert len(rows) == 1
    stored = rows[0]
    assert stored["key_hash"] == hash_key(key)
    assert key not in str(dict(stored))
    # the hash is not reversible to the key, and is not the key itself
    assert stored["key_hash"] != key
    assert len(stored["key_hash"]) == 64


# --- authenticating -----------------------------------------------------------


def test_api_key_authenticates_the_data_plane(client: TestClient) -> None:
    _, key = _new_key(client, _jwt_headers(client))
    auth = {"X-API-Key": key}

    ingest = client.post(INGEST, json={"session_tag": "s1", "text": TEXT}, headers=auth)
    assert ingest.status_code == 200
    assert ingest.json()["handle"].startswith("shm_")

    query = client.post(
        QUERY, json={"session_tag": "s1", "query": "what is my budget?"}, headers=auth
    )
    assert query.status_code == 200
    assert query.json()["subset"]["constraints"]["budget"]["max"]["value"] == 2000

    assert client.get(USAGE, headers=auth).status_code == 200


def test_no_credential_is_rejected(client: TestClient) -> None:
    assert client.post(INGEST, json={"session_tag": "s1", "text": TEXT}).status_code == 401


@pytest.mark.parametrize("bad", [
    "sj_live_totally-made-up-key-value",
    "not-even-the-right-prefix",
    "",
])
def test_invalid_api_key_is_rejected(client: TestClient, bad: str) -> None:
    _new_key(client, _jwt_headers(client))  # a real key exists, but not this one
    resp = client.post(
        INGEST, json={"session_tag": "s1", "text": TEXT}, headers={"X-API-Key": bad}
    )
    assert resp.status_code == 401


def test_jwt_still_works_unchanged(client: TestClient) -> None:
    """The console flow must be untouched by the new header."""
    headers = _jwt_headers(client)
    assert client.post(
        INGEST, json={"session_tag": "s1", "text": TEXT}, headers=headers
    ).status_code == 200
    assert client.get(USAGE, headers=headers).status_code == 200


def test_key_sees_only_its_owners_data(client: TestClient) -> None:
    owner = _jwt_headers(client, "owner@example.com")
    client.post(INGEST, json={"session_tag": "s1", "text": TEXT}, headers=owner)

    other = _jwt_headers(client, "other@example.com")
    _, other_key = _new_key(client, other)

    # the other user's key has no state of its own, so query 404s rather
    # than returning the owner's
    resp = client.post(
        QUERY, json={"session_tag": "s1", "query": "what is my budget?"},
        headers={"X-API-Key": other_key},
    )
    assert resp.status_code == 404
    assert "Ayaan" not in resp.text
    assert client.get(USAGE, headers={"X-API-Key": other_key}).json()["total_states"] == 0


# --- scope: a key is not a session --------------------------------------------


@pytest.mark.parametrize("method,path", [
    ("post", GENERATE),          # minting more keys
    ("get", LIST),               # enumerating keys
    ("get", PROVIDER_KEYS),      # reading the user's OpenRouter credit
])
def test_api_key_cannot_reach_account_management(
    client: TestClient, method: str, path: str
) -> None:
    """A leaked key must not escalate into a foothold or the provider key."""
    _, key = _new_key(client, _jwt_headers(client))
    resp = getattr(client, method)(path, headers={"X-API-Key": key})
    assert resp.status_code == 401


# --- revoking -----------------------------------------------------------------


def test_revoked_key_stops_working_immediately(client: TestClient) -> None:
    headers = _jwt_headers(client)
    key_id, key = _new_key(client, headers)
    auth = {"X-API-Key": key}

    assert client.post(
        INGEST, json={"session_tag": "s1", "text": TEXT}, headers=auth
    ).status_code == 200

    revoke = client.delete(f"{LIST}/{key_id}", headers=headers)
    assert revoke.status_code == 200
    assert revoke.json() == {"id": key_id, "revoked": True}

    assert client.post(
        INGEST, json={"session_tag": "s1", "text": TEXT}, headers=auth
    ).status_code == 401
    # the row stays listed, marked revoked: a developer whose .env stopped
    # working needs to see *why*, not find the key silently gone
    listed = client.get(LIST, headers=headers).json()
    assert [k["status"] for k in listed] == ["revoked"]
    assert listed[0]["revoked"] is True


def test_revoking_twice_is_not_found(client: TestClient) -> None:
    headers = _jwt_headers(client)
    key_id, _ = _new_key(client, headers)
    assert client.delete(f"{LIST}/{key_id}", headers=headers).status_code == 200
    assert client.delete(f"{LIST}/{key_id}", headers=headers).status_code == 404


def test_cannot_revoke_another_users_key(client: TestClient) -> None:
    victim = _jwt_headers(client, "victim@example.com")
    key_id, key = _new_key(client, victim)

    attacker = _jwt_headers(client, "mallory@example.com")
    assert client.delete(f"{LIST}/{key_id}", headers=attacker).status_code == 404

    # still working — the attempt changed nothing
    assert client.post(
        INGEST, json={"session_tag": "s1", "text": TEXT}, headers={"X-API-Key": key}
    ).status_code == 200


def test_revoking_one_key_leaves_the_others(client: TestClient) -> None:
    headers = _jwt_headers(client)
    first_id, first = _new_key(client, headers)
    _, second = _new_key(client, headers)

    client.delete(f"{LIST}/{first_id}", headers=headers)
    assert client.post(
        INGEST, json={"session_tag": "s1", "text": TEXT}, headers={"X-API-Key": first}
    ).status_code == 401
    assert client.post(
        INGEST, json={"session_tag": "s2", "text": TEXT}, headers={"X-API-Key": second}
    ).status_code == 200


# --- usage --------------------------------------------------------------------


def test_usage_counts_and_token_estimate(client: TestClient) -> None:
    headers = _jwt_headers(client)
    _, key = _new_key(client, headers)
    auth = {"X-API-Key": key}

    empty = client.get(USAGE, headers=auth).json()
    assert empty == {
        "requests_today": 0, "total_states": 0,
        "total_audit_rows": 0, "est_tokens_saved": 0,
    }

    client.post(INGEST, json={"session_tag": "s1", "text": TEXT}, headers=auth)
    # audit=true records the disclosure without needing a provider key
    for _ in range(3):
        client.post(
            QUERY,
            json={"session_tag": "s1", "query": "what is my budget?", "audit": True},
            headers=auth,
        )

    body = client.get(USAGE, headers=auth).json()
    assert body["total_states"] == 1
    assert body["total_audit_rows"] == 3
    assert body["requests_today"] == 3
    # three disclosures, each smaller than the full state
    assert body["est_tokens_saved"] > 0


def test_usage_token_estimate_grows_with_disclosures(client: TestClient) -> None:
    headers = _jwt_headers(client)
    client.post(INGEST, json={"session_tag": "s1", "text": TEXT}, headers=headers)
    payload = {"session_tag": "s1", "query": "what is my budget?", "audit": True}

    client.post(QUERY, json=payload, headers=headers)
    after_one = client.get(USAGE, headers=headers).json()["est_tokens_saved"]
    client.post(QUERY, json=payload, headers=headers)
    after_two = client.get(USAGE, headers=headers).json()["est_tokens_saved"]

    assert after_one > 0
    # Same disclosure twice, so the saving doubles. The estimate floors
    # chars//4 once over the summed total, so the doubled figure can land one
    # token above 2x the individually-floored one.
    assert after_two - 2 * after_one in (0, 1)


def test_usage_requires_a_credential(client: TestClient) -> None:
    assert client.get(USAGE).status_code == 401


# --- key lifecycle: expiry, labels, status, last used -------------------------


def test_generate_defaults_to_thirty_days(client: TestClient) -> None:
    from datetime import datetime

    body = client.post(GENERATE, headers=_jwt_headers(client)).json()
    assert body["expires_at"] is not None
    created = datetime.fromisoformat(body["created_at"])
    expires = datetime.fromisoformat(body["expires_at"])
    assert 29 <= (expires - created).days <= 30


@pytest.mark.parametrize("choice,days", [("7d", 7), ("30d", 30), ("365d", 365)])
def test_generate_honours_expiry_choice(client: TestClient, choice: str, days: int) -> None:
    from datetime import datetime

    body = client.post(GENERATE, json={"expires_in": choice},
                       headers=_jwt_headers(client)).json()
    created = datetime.fromisoformat(body["created_at"])
    expires = datetime.fromisoformat(body["expires_at"])
    assert (expires - created).days in (days - 1, days)


def test_never_expires(client: TestClient) -> None:
    body = client.post(GENERATE, json={"expires_in": "never"},
                       headers=_jwt_headers(client)).json()
    assert body["expires_at"] is None
    assert client.get(LIST, headers=_jwt_headers(client)).json()[0]["status"] == "active"


def test_unknown_expiry_is_rejected(client: TestClient) -> None:
    resp = client.post(GENERATE, json={"expires_in": "forever-ish"},
                       headers=_jwt_headers(client))
    assert resp.status_code == 422


def test_label_is_stored_and_listed(client: TestClient) -> None:
    headers = _jwt_headers(client)
    client.post(GENERATE, json={"expires_in": "30d", "label": "CI pipeline"},
                headers=headers)
    assert client.get(LIST, headers=headers).json()[0]["label"] == "CI pipeline"


def test_expired_key_is_rejected_with_the_date(client: TestClient) -> None:
    """A generic 401 sends people hunting for a typo; the date ends it."""
    from datetime import datetime, timedelta, timezone

    from app.apikeys import api_keys as api_keys_table

    headers = _jwt_headers(client)
    _, key = _new_key(client, headers)
    expired_on = datetime.now(timezone.utc) - timedelta(days=2)

    db = _TestSession()
    try:
        db.execute(api_keys_table.update().values(expires_at=expired_on))
        db.commit()
    finally:
        db.close()

    resp = client.post(INGEST, json={"session_tag": "s1", "text": TEXT},
                       headers={"X-API-Key": key})
    assert resp.status_code == 401
    detail = resp.json()["detail"]
    assert "expired" in detail.lower()
    assert expired_on.date().isoformat() in detail


def test_status_reflects_the_clock(client: TestClient) -> None:
    from datetime import datetime, timedelta, timezone

    from app.apikeys import api_keys as api_keys_table

    headers = _jwt_headers(client)
    key_id, _ = _new_key(client, headers)
    now = datetime.now(timezone.utc)

    for delta, expected in [
        (timedelta(days=40), "active"),
        (timedelta(days=3), "expiring_soon"),
        (timedelta(days=-1), "expired"),
    ]:
        db = _TestSession()
        try:
            db.execute(api_keys_table.update()
                       .where(api_keys_table.c.id == key_id)
                       .values(expires_at=now + delta))
            db.commit()
        finally:
            db.close()
        listed = client.get(LIST, headers=headers).json()
        assert listed[0]["status"] == expected, expected


def test_last_used_at_is_recorded(client: TestClient) -> None:
    headers = _jwt_headers(client)
    _, key = _new_key(client, headers)
    assert client.get(LIST, headers=headers).json()[0]["last_used_at"] is None

    client.post(INGEST, json={"session_tag": "s1", "text": TEXT},
                headers={"X-API-Key": key})
    assert client.get(LIST, headers=headers).json()[0]["last_used_at"] is not None
