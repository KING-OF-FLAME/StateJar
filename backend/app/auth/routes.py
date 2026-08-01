"""Auth routes: signup, login, and the get_current_user dependency."""

from __future__ import annotations

from datetime import datetime, timezone

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import users
from app.auth.security import create_access_token, decode_token, hash_password, verify_password
from app.database import get_db
from app.security import LOGIN_LIMIT, SIGNUP_LIMIT, limiter

router = APIRouter(prefix="/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: str = "user"


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(SIGNUP_LIMIT)  # per IP: bulk account creation
def signup(
    request: Request, body: SignupRequest, db: Session = Depends(get_db)
) -> UserOut:
    existing = db.execute(
        select(users.c.id).where(users.c.email == body.email)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")

    result = db.execute(
        users.insert().values(
            email=body.email,
            password_hash=hash_password(body.password),
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    return UserOut(id=result.inserted_primary_key[0], email=body.email)


@router.post("/login", response_model=TokenOut)
@limiter.limit(LOGIN_LIMIT)  # per IP: credential stuffing
def login(
    request: Request, body: LoginRequest, db: Session = Depends(get_db)
) -> TokenOut:
    row = db.execute(
        select(users).where(users.c.email == body.email)
    ).mappings().first()
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    return TokenOut(access_token=create_access_token(row["id"], row["email"]))


def user_from_bearer(
    credentials: HTTPAuthorizationCredentials | None, db: Session
) -> UserOut:
    """Resolve a bearer token to its user, or raise 401.

    Shared with the developer-API dependency so both entry points validate a
    JWT identically — the console flow is the one implementation.
    """
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
    except pyjwt.PyJWTError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = int(payload["sub"])
    row = db.execute(select(users).where(users.c.id == user_id)).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user no longer exists")
    return UserOut(id=row["id"], email=row["email"])


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> UserOut:
    """JWT dependency for console routes (account and key management)."""
    return user_from_bearer(credentials, db)
