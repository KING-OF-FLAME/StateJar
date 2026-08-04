"""Profile: read, update, isolation between accounts, and fail-closed validation."""

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
from app.profile import LIMITS, profile_metadata, user_profiles

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def _schema() -> Generator[None, None, None]:
    for md in (auth_metadata, apikeys_metadata, profile_metadata):
        md.create_all(engine)
    yield
    for md in (auth_metadata, apikeys_metadata, profile_metadata):
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


def register(client: TestClient, email: str) -> dict[str, str]:
    client.post("/api/v1/auth/signup", json={"email": email, "password": "s3cretpass"})
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "s3cretpass"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def headers(client: TestClient) -> dict[str, str]:
    return register(client, "p1@example.com")


# --------------------------------------------------------------------------
# read / update
# --------------------------------------------------------------------------

def test_profile_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/profile").status_code == 401
    assert client.patch("/api/v1/profile", json={"role": "x"}).status_code == 401


def test_unset_profile_reads_empty_rather_than_404(
    client: TestClient, headers: dict[str, str]
) -> None:
    """Never having filled one in is a normal state, not an error."""
    r = client.get("/api/v1/profile", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["exists"] is False
    assert body["display_name"] is None
    assert body["created_at"] is None


def test_update_then_read_round_trip(
    client: TestClient, headers: dict[str, str]
) -> None:
    r = client.patch("/api/v1/profile", headers=headers, json={
        "display_name": "Meera Nair",
        "organization": "ReliefNet",
        "role": "Coordinator",
        "use_case": "Disaster relief logistics",
    })
    assert r.status_code == 200, r.text
    assert r.json()["display_name"] == "Meera Nair"
    assert r.json()["exists"] is True

    again = client.get("/api/v1/profile", headers=headers).json()
    assert again["organization"] == "ReliefNet"
    assert again["role"] == "Coordinator"
    assert again["use_case"] == "Disaster relief logistics"
    assert again["created_at"] and again["updated_at"]


def test_patch_leaves_absent_fields_alone(
    client: TestClient, headers: dict[str, str]
) -> None:
    """A PATCH is a partial update; omitting a field must not blank it."""
    client.patch("/api/v1/profile", headers=headers,
                 json={"display_name": "Meera", "organization": "ReliefNet"})
    client.patch("/api/v1/profile", headers=headers, json={"role": "Coordinator"})

    body = client.get("/api/v1/profile", headers=headers).json()
    assert body["display_name"] == "Meera"      # untouched by the second patch
    assert body["organization"] == "ReliefNet"
    assert body["role"] == "Coordinator"


def test_explicit_null_clears_a_field(
    client: TestClient, headers: dict[str, str]
) -> None:
    """Sending null is different from omitting: it means "remove this"."""
    client.patch("/api/v1/profile", headers=headers, json={"organization": "ReliefNet"})
    client.patch("/api/v1/profile", headers=headers, json={"organization": None})
    assert client.get("/api/v1/profile", headers=headers).json()["organization"] is None


def test_blank_string_clears_a_field(
    client: TestClient, headers: dict[str, str]
) -> None:
    client.patch("/api/v1/profile", headers=headers, json={"role": "Coordinator"})
    client.patch("/api/v1/profile", headers=headers, json={"role": "   "})
    assert client.get("/api/v1/profile", headers=headers).json()["role"] is None


def test_one_row_per_account(client: TestClient, headers: dict[str, str]) -> None:
    for value in ("A", "B", "C"):
        client.patch("/api/v1/profile", headers=headers, json={"role": value})
    with TestingSession() as db:
        rows = db.execute(user_profiles.select()).mappings().all()
    assert len(rows) == 1
    assert rows[0]["role"] == "C"


# --------------------------------------------------------------------------
# isolation
# --------------------------------------------------------------------------

def test_one_user_cannot_read_anothers_profile(client: TestClient) -> None:
    a = register(client, "a@example.com")
    b = register(client, "b@example.com")
    client.patch("/api/v1/profile", headers=a,
                 json={"display_name": "Account A", "organization": "A Corp"})

    seen = client.get("/api/v1/profile", headers=b).json()
    assert seen["exists"] is False
    assert seen["display_name"] is None
    assert "A Corp" not in str(seen)


def test_one_user_cannot_write_anothers_profile(client: TestClient) -> None:
    """There is no id to pass, so B's write can only ever create B's own row."""
    a = register(client, "a2@example.com")
    b = register(client, "b2@example.com")
    client.patch("/api/v1/profile", headers=a, json={"display_name": "Account A"})
    client.patch("/api/v1/profile", headers=b, json={"display_name": "Account B"})

    assert client.get("/api/v1/profile", headers=a).json()["display_name"] == "Account A"
    assert client.get("/api/v1/profile", headers=b).json()["display_name"] == "Account B"
    with TestingSession() as db:
        assert len(db.execute(user_profiles.select()).mappings().all()) == 2


def test_a_client_supplied_user_id_is_ignored(client: TestClient) -> None:
    """Scope comes from the credential; a body field must not redirect the write."""
    a = register(client, "a3@example.com")
    b = register(client, "b3@example.com")
    victim = client.get("/api/v1/profile", headers=b)   # ensure B exists as an account
    assert victim.status_code == 200

    client.patch("/api/v1/profile", headers=a,
                 json={"display_name": "Attacker", "user_id": 999, "id": 1})
    assert client.get("/api/v1/profile", headers=b).json()["display_name"] is None
    assert client.get("/api/v1/profile", headers=a).json()["display_name"] == "Attacker"


# --------------------------------------------------------------------------
# validation — reject, never coerce
# --------------------------------------------------------------------------

def test_overlong_value_is_rejected_with_a_field_reason(
    client: TestClient, headers: dict[str, str]
) -> None:
    r = client.patch("/api/v1/profile", headers=headers,
                     json={"display_name": "x" * (LIMITS["display_name"] + 1)})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "profile rejected"
    assert "display_name" in detail["fields"]
    assert str(LIMITS["display_name"]) in detail["fields"]["display_name"]


def test_rejected_value_is_not_truncated_and_stored(
    client: TestClient, headers: dict[str, str]
) -> None:
    """Fail closed: a value that did not pass must not be silently reshaped."""
    client.patch("/api/v1/profile", headers=headers, json={"role": "Coordinator"})
    client.patch("/api/v1/profile", headers=headers,
                 json={"role": "y" * (LIMITS["role"] + 50)})
    assert client.get("/api/v1/profile", headers=headers).json()["role"] == "Coordinator"


def test_control_characters_are_rejected(
    client: TestClient, headers: dict[str, str]
) -> None:
    r = client.patch("/api/v1/profile", headers=headers,
                     json={"display_name": "Meera\nNair"})
    assert r.status_code == 422
    assert "display_name" in r.json()["detail"]["fields"]


def test_one_bad_field_rejects_the_whole_request(
    client: TestClient, headers: dict[str, str]
) -> None:
    """A partial write would leave the user unsure which half survived."""
    r = client.patch("/api/v1/profile", headers=headers, json={
        "organization": "ReliefNet",                       # fine
        "role": "z" * (LIMITS["role"] + 1),                # not
    })
    assert r.status_code == 422
    assert client.get("/api/v1/profile", headers=headers).json()["organization"] is None


def test_every_bad_field_is_reported_at_once(
    client: TestClient, headers: dict[str, str]
) -> None:
    r = client.patch("/api/v1/profile", headers=headers, json={
        "display_name": "a" * 200,
        "role": "b" * 200,
    })
    assert set(r.json()["detail"]["fields"]) == {"display_name", "role"}


def test_unknown_fields_alone_are_rejected(
    client: TestClient, headers: dict[str, str]
) -> None:
    r = client.patch("/api/v1/profile", headers=headers, json={"favourite_colour": "teal"})
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "no recognised fields to update"


def test_non_string_value_is_rejected(
    client: TestClient, headers: dict[str, str]
) -> None:
    r = client.patch("/api/v1/profile", headers=headers, json={"role": 42})
    assert r.status_code == 422


def test_surrounding_whitespace_is_trimmed(
    client: TestClient, headers: dict[str, str]
) -> None:
    """The one liberty taken, because a trailing space is a typing artefact."""
    client.patch("/api/v1/profile", headers=headers, json={"display_name": "  Meera  "})
    assert client.get("/api/v1/profile", headers=headers).json()["display_name"] == "Meera"


def test_profile_stores_no_message_text(
    client: TestClient, headers: dict[str, str]
) -> None:
    """The profile must not become a back door for the thing storage refuses.

    `storage._assert_no_transcript` keeps raw conversation out of state. A
    free-text profile field is exactly the shape that could quietly reintroduce
    it, so the columns are capped and single-line by design — long enough for a
    use case, far too short for a transcript.
    """
    assert max(LIMITS.values()) <= 400
    long_text = "user: hello\nassistant: hi\n" * 40
    r = client.patch("/api/v1/profile", headers=headers, json={"use_case": long_text})
    assert r.status_code == 422
