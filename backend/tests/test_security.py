"""Security regression tests.

Two kinds live here:

  * behavioural — hit the running app and assert an attack is refused;
  * static — parse app/ and assert a class of bug cannot be reintroduced
    (raw SQL built by interpolation, secrets handed to the logger).

The static ones are the reason this file scans source: a passing SQLi test
only proves today's query is safe, not tomorrow's.
"""

from __future__ import annotations

import ast
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt as pyjwt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from slowapi.util import get_remote_address
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from tests.conftest import fake_key
from app.auth.models import auth_metadata, users
from app.auth.routes import UserOut, get_current_user
from app.auth.security import TOKEN_TTL, create_access_token
from app.config import get_settings
from app.database import get_db
from app.llm.gateway import decrypt_key, encrypt_key, llm_metadata
from app.main import api_v1, app
from app.memory.audit import audit_metadata
from app.memory.storage import metadata as storage_metadata
from app.security import SECURITY_HEADERS, limiter, user_or_ip

APP_DIR = Path(__file__).resolve().parent.parent / "app"

SIGNUP = "/api/v1/auth/signup"
LOGIN = "/api/v1/auth/login"
KEYS = "/api/v1/keys/provider"
WHOAMI = "/api/v1/auth/whoami"

EMAIL = "ayaan@example.com"
PASSWORD = "s3cretpass"

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


# own protected route, so this file does not depend on test_auth registering one
@api_v1.get("/auth/whoami", response_model=UserOut)
def _whoami(user: UserOut = Depends(get_current_user)) -> UserOut:
    return user


app.include_router(api_v1)


@pytest.fixture(autouse=True)
def client() -> Generator[TestClient, None, None]:
    for md in (auth_metadata, llm_metadata, storage_metadata, audit_metadata):
        md.drop_all(_engine)
        md.create_all(_engine)
    app.dependency_overrides[get_db] = _test_db
    limiter.reset()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    limiter.enabled = False
    limiter.reset()


def _signup(client: TestClient, email: str = EMAIL) -> None:
    client.post(SIGNUP, json={"email": email, "password": PASSWORD})


def _token(client: TestClient) -> str:
    return client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD}).json()["access_token"]


def _auth(client: TestClient) -> dict[str, str]:
    _signup(client)
    return {"Authorization": f"Bearer {_token(client)}"}


# --- injection ----------------------------------------------------------------

SQLI_PAYLOADS = [
    "' OR '1'='1",
    "admin'--",
    "' OR 1=1--",
    "'; DROP TABLE users;--",
    "' UNION SELECT password_hash FROM users--",
]


@pytest.mark.parametrize("payload", SQLI_PAYLOADS)
def test_sqli_on_login_is_refused(client: TestClient, payload: str) -> None:
    """Injection in either field must never authenticate."""
    _signup(client)
    for body in (
        {"email": payload, "password": PASSWORD},
        {"email": EMAIL, "password": payload},
    ):
        resp = client.post(LOGIN, json=body)
        assert resp.status_code in (401, 422), resp.text
        assert "access_token" not in resp.text


def test_sqli_does_not_execute(client: TestClient) -> None:
    """The DROP TABLE payload must be treated as a string, not as SQL."""
    _signup(client)
    client.post(LOGIN, json={"email": "'; DROP TABLE users;--", "password": PASSWORD})

    db = _TestSession()
    try:
        rows = db.execute(select(users.c.email)).scalars().all()
    finally:
        db.close()
    assert rows == [EMAIL]  # table intact, account intact
    assert client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD}).status_code == 200


def test_no_dynamically_built_sql_in_app_code() -> None:
    """Every text()/exec_driver_sql() argument must be a literal.

    AST rather than grep: an f-string, a .format() call and a % expression
    are all different node types, and all of them are findable here.
    """
    offenders: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name not in ("text", "exec_driver_sql"):
                continue
            for arg in node.args:
                if not _is_literal_string(arg):
                    offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], f"raw SQL built dynamically: {offenders}"


def _is_literal_string(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    # "a" "b" folds to one Constant; "a" + "b" stays a BinOp of Constants
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_literal_string(node.left) and _is_literal_string(node.right)
    return False  # JoinedStr (f-string), .format(), % — all rejected


# --- secrets never leave the process ------------------------------------------

FULL_KEY = fake_key("or-full-secret")

SECRET_NAMES = ("api_key", "secret", "password", "plaintext", "encrypted_key")


def test_saving_a_key_never_echoes_it(client: TestClient) -> None:
    headers = _auth(client)
    resp = client.post(KEYS, json={"provider": "openrouter", "api_key": FULL_KEY}, headers=headers)
    assert resp.status_code == 201
    assert FULL_KEY not in resp.text
    assert resp.json()["key_last4"] == FULL_KEY[-4:]


def test_keys_listing_has_no_full_key(client: TestClient) -> None:
    headers = _auth(client)
    client.post(KEYS, json={"provider": "openrouter", "api_key": FULL_KEY}, headers=headers)

    resp = client.get(KEYS, headers=headers)
    assert resp.status_code == 200
    assert FULL_KEY not in resp.text
    # nothing beyond the last 4 characters is disclosed
    assert FULL_KEY[:-4] not in resp.text
    entry = resp.json()[0]
    assert entry["key_last4"] == FULL_KEY[-4:]
    assert not any(k in entry for k in ("api_key", "key", "encrypted_key"))


def test_another_user_cannot_see_your_keys(client: TestClient) -> None:
    owner = _auth(client)
    client.post(KEYS, json={"provider": "openrouter", "api_key": FULL_KEY}, headers=owner)

    _signup(client, "mallory@example.com")
    token = client.post(
        LOGIN, json={"email": "mallory@example.com", "password": PASSWORD}
    ).json()["access_token"]
    resp = client.get(KEYS, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_tampered_ciphertext_rejected() -> None:
    """AES-GCM's auth tag must make an edited blob unusable, not silently wrong."""
    blob = encrypt_key(FULL_KEY)
    assert FULL_KEY.encode() not in blob  # not merely encoded
    assert decrypt_key(blob) == FULL_KEY

    for position in (0, len(blob) // 2, len(blob) - 1):  # nonce, body, tag
        edited = bytearray(blob)
        edited[position] ^= 0x01
        with pytest.raises(Exception):
            decrypt_key(bytes(edited))


def test_state_by_handle_scoped_to_user(client: TestClient) -> None:
    """A handle is content-addressed, not a capability: knowing one is not
    authorisation to read the state behind it."""
    owner = _auth(client)
    ingest = client.post(
        "/api/v1/memory/ingest",
        json={"session_tag": "s1", "text": "My name is Ayaan, budget under ₹2000."},
        headers=owner,
    )
    assert ingest.status_code == 200
    handle = ingest.json()["handle"]
    assert client.get(f"/api/v1/memory/state/{handle}", headers=owner).status_code == 200

    _signup(client, "mallory@example.com")
    token = client.post(
        LOGIN, json={"email": "mallory@example.com", "password": PASSWORD}
    ).json()["access_token"]
    stolen = client.get(
        f"/api/v1/memory/state/{handle}", headers={"Authorization": f"Bearer {token}"}
    )
    assert stolen.status_code == 404
    assert "Ayaan" not in stolen.text


def test_no_secret_is_ever_handed_to_the_logger() -> None:
    """Static guard: log records travel to stdout and any aggregator."""
    offenders: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            target = node.func.value
            is_logger = (
                isinstance(target, ast.Name) and "log" in target.id.lower()
            ) or (isinstance(target, ast.Attribute) and "log" in target.attr.lower())
            if not (is_logger or node.func.attr == "print"):
                continue
            for arg in ast.walk(node):
                referenced = (
                    arg.id if isinstance(arg, ast.Name)
                    else arg.attr if isinstance(arg, ast.Attribute)
                    else ""
                )
                if any(s in referenced.lower() for s in SECRET_NAMES):
                    offenders.append(f"{path.name}:{node.lineno} -> {referenced}")
    assert offenders == [], f"secret passed to a logger: {offenders}"


# --- JWT ----------------------------------------------------------------------


def _forge(payload: dict, secret: str = "", algorithm: str = "HS256") -> str:
    return pyjwt.encode(payload, secret or get_settings().jwt_secret, algorithm=algorithm)


def test_valid_token_is_accepted(client: TestClient) -> None:
    assert client.get(WHOAMI, headers=_auth(client)).status_code == 200


def test_expired_token_is_rejected(client: TestClient) -> None:
    _signup(client)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    token = _forge({"sub": "1", "email": EMAIL, "role": "user",
                    "iat": past - timedelta(hours=1), "exp": past})
    resp = client.get(WHOAMI, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


def test_token_signed_with_another_secret_is_rejected(client: TestClient) -> None:
    _signup(client)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    token = _forge({"sub": "1", "exp": future}, secret="attacker-controlled-secret")
    assert client.get(WHOAMI, headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_unsigned_token_is_rejected(client: TestClient) -> None:
    """alg=none must not be honoured — decode pins HS256."""
    _signup(client)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    token = pyjwt.encode({"sub": "1", "exp": future}, key="", algorithm="none")
    assert client.get(WHOAMI, headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_tokens_carry_a_bounded_lifetime() -> None:
    """A token with no exp would never be revocable."""
    assert timedelta(0) < TOKEN_TTL <= timedelta(days=7)
    claims = pyjwt.decode(
        create_access_token(1, EMAIL), get_settings().jwt_secret, algorithms=["HS256"]
    )
    assert "exp" in claims and "iat" in claims
    assert claims["exp"] - claims["iat"] == TOKEN_TTL.total_seconds()


# --- rate limits --------------------------------------------------------------


def test_sixth_rapid_login_is_rate_limited(client: TestClient) -> None:
    """Credential stuffing: failed attempts must count too."""
    _signup(client)
    limiter.reset()
    limiter.enabled = True

    codes = [
        client.post(LOGIN, json={"email": EMAIL, "password": "wrongpass1"}).status_code
        for _ in range(6)
    ]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429


def test_rate_limited_response_still_carries_security_headers(client: TestClient) -> None:
    _signup(client)
    limiter.reset()
    limiter.enabled = True
    for _ in range(6):
        resp = client.post(LOGIN, json={"email": EMAIL, "password": "wrongpass1"})
    assert resp.status_code == 429
    for header, value in SECURITY_HEADERS.items():
        assert resp.headers.get(header) == value


def test_eleventh_signup_is_rate_limited(client: TestClient) -> None:
    limiter.reset()
    limiter.enabled = True
    codes = [
        client.post(SIGNUP, json={"email": EMAIL, "password": PASSWORD}).status_code
        for _ in range(11)
    ]
    assert codes[0] == 201
    assert codes[1:10] == [409] * 9  # duplicates, but still counted
    assert codes[10] == 429


def _request(headers: dict[str, str], host: str = "1.2.3.4") -> Request:
    """A genuine Starlette Request — its headers are case-insensitive, and a
    stand-in dict would hide a lookup bug rather than catch it."""
    return Request({
        "type": "http", "method": "POST", "path": "/api/v1/chat", "scheme": "http",
        "server": ("testserver", 80), "query_string": b"", "client": (host, 12345),
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    })


def test_chat_limit_is_keyed_per_user(client: TestClient) -> None:
    """Two accounts behind one NAT must not share a /chat budget."""
    assert user_or_ip(_request(_auth(client))).startswith("user:")

    # no token, or one that will be rejected downstream anyway: fall back to IP
    assert user_or_ip(_request({})) == "1.2.3.4"
    assert user_or_ip(_request({"Authorization": "Bearer not.a.jwt"})) == "1.2.3.4"

    past = datetime.now(timezone.utc) - timedelta(hours=1)
    expired = _forge({"sub": "1", "exp": past})
    assert user_or_ip(_request({"Authorization": f"Bearer {expired}"})) == "1.2.3.4"


def test_the_three_limits_are_actually_registered() -> None:
    """Guards the wiring: a decorator dropped in a refactor fails here."""
    registered = {
        name.rsplit(".", 1)[-1]: (str(lim.limit), lim.key_func)
        for name, limits in limiter._route_limits.items()
        for lim in limits
    }
    assert registered["login"][0] == "5 per 1 minute"
    assert registered["signup"][0] == "10 per 1 hour"
    assert registered["chat"] == ("60 per 1 hour", user_or_ip)
    # login/signup stay per-IP: there is no authenticated user yet
    assert registered["login"][1] is get_remote_address
    assert registered["signup"][1] is get_remote_address


# --- headers and CORS ---------------------------------------------------------


def test_security_headers_on_every_response(client: TestClient) -> None:
    for resp in (
        client.get("/api/v1/health"),
        client.get(WHOAMI),                       # 401
        client.post(LOGIN, json={"email": "no@example.com", "password": PASSWORD}),
    ):
        for header, value in SECURITY_HEADERS.items():
            assert resp.headers.get(header) == value, f"{header} missing on {resp.status_code}"


def test_cors_allowlist_is_exact() -> None:
    origins = get_settings().cors_origins
    assert "*" not in origins
    assert all(o.startswith(("http://localhost", "http://127.0.0.1", "https://")) for o in origins)
    # both apex and www, or a signup from one of them fails
    assert "https://statejar.com" in origins
    assert "https://www.statejar.com" in origins


def test_unknown_origin_is_not_allowed(client: TestClient) -> None:
    resp = client.options(
        LOGIN,
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example"


def test_known_origin_is_allowed(client: TestClient) -> None:
    resp = client.options(
        LOGIN,
        headers={
            "Origin": "https://statejar.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "https://statejar.com"


# --- deployment safety --------------------------------------------------------


def test_ml_extras_stay_out_of_requirements() -> None:
    """Railway installs requirements.txt only.

    torch alone is multi-GB; letting it into the production manifest turns a
    30-second build into one that times out. The optional tiers live in
    requirements-ml.txt and degrade silently when absent, so this separation
    is load-bearing rather than tidiness. It has been broken by an editor
    once already, hence a test rather than a habit.
    """
    backend = Path(__file__).resolve().parent.parent
    production = (backend / "requirements.txt").read_text(encoding="utf-8").lower()
    heavy = ("torch", "gliner", "sentence-transformers", "transformers", "nvidia-")

    offenders = [
        line.strip()
        for line in production.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
        and any(pkg in line for pkg in heavy)
    ]
    assert offenders == [], (
        f"ML extras must stay in requirements-ml.txt, found: {offenders}"
    )

    # and they must actually be declared somewhere, or the tiers are dead code
    optional = (backend / "requirements-ml.txt").read_text(encoding="utf-8").lower()
    for pkg in ("torch", "gliner", "sentence-transformers"):
        assert pkg in optional, f"{pkg} missing from requirements-ml.txt"
