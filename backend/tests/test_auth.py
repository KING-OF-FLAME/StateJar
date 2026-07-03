"""Tests for signup, login, and the JWT get_current_user dependency."""

from collections.abc import Generator

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.models import auth_metadata
from app.auth.routes import UserOut, get_current_user
from app.database import get_db
from app.main import api_v1, app

# one shared in-memory SQLite across all connections
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


# a minimal protected route to exercise get_current_user
@api_v1.get("/auth/me", response_model=UserOut)
def me(user: UserOut = Depends(get_current_user)) -> UserOut:
    return user


app.include_router(api_v1)  # re-include to register /me


@pytest.fixture(autouse=True)
def client() -> Generator[TestClient, None, None]:
    auth_metadata.drop_all(_engine)
    auth_metadata.create_all(_engine)
    app.dependency_overrides[get_db] = _test_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _signup(c: TestClient, email: str = "ayaan@example.com", password: str = "s3cretpass") -> dict:
    return c.post("/api/v1/auth/signup", json={"email": email, "password": password}).json()


def test_signup_creates_user(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/signup", json={"email": "ayaan@example.com", "password": "s3cretpass"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "ayaan@example.com"
    assert body["role"] == "user"
    assert "password" not in body and "password_hash" not in body


def test_duplicate_email_rejected(client: TestClient) -> None:
    _signup(client)
    resp = client.post(
        "/api/v1/auth/signup", json={"email": "ayaan@example.com", "password": "s3cretpass"}
    )
    assert resp.status_code == 409


def test_short_password_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/signup", json={"email": "a@example.com", "password": "short"}
    )
    assert resp.status_code == 422


def test_login_returns_jwt(client: TestClient) -> None:
    _signup(client)
    resp = client.post(
        "/api/v1/auth/login", json={"email": "ayaan@example.com", "password": "s3cretpass"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"].count(".") == 2  # JWT shape


def test_login_wrong_password_rejected(client: TestClient) -> None:
    _signup(client)
    resp = client.post(
        "/api/v1/auth/login", json={"email": "ayaan@example.com", "password": "wrongpass1"}
    )
    assert resp.status_code == 401


def test_protected_route_with_valid_token(client: TestClient) -> None:
    _signup(client)
    token = client.post(
        "/api/v1/auth/login", json={"email": "ayaan@example.com", "password": "s3cretpass"}
    ).json()["access_token"]
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "ayaan@example.com"


def test_protected_route_rejects_missing_and_bad_tokens(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401
