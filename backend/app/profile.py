"""User profile: who the account belongs to, in four optional fields.

A separate table rather than columns on `users`, for one reason: `users` holds
the credential. Every read of it is an auth path, and widening an auth-path row
with display data means profile edits touch the table that decides who you are.
A one-to-one side table keeps the credential surface exactly as small as it was.

Scope is deliberately four fields. Nothing sensitive, no uploads, no avatar
bytes — a profile that cannot hold a file cannot leak one, and the finale does
not need a settings suite.

Validation is fail-closed and matches the rest of the project: a value that does
not pass is **rejected with a reason**, never trimmed into shape and stored. The
same principle the extractor applies to a budget applies to a job title — a
system that silently rewrites your input is a system you cannot trust about what
it kept.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    select,
)
from sqlalchemy.orm import Session

from app.auth.routes import UserOut, get_current_user
from app.database import get_db
from app.timeutil import iso_utc

profile_metadata = MetaData()

user_profiles = Table(
    "user_profiles",
    profile_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    # one row per account; the unique constraint is what makes "one profile"
    # a property of the schema rather than of the code that happens to write it
    Column("user_id", Integer, nullable=False, unique=True),
    Column("display_name", String(80), nullable=True),
    Column("organization", String(120), nullable=True),
    Column("role", String(80), nullable=True),
    Column("use_case", String(400), nullable=True),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

router = APIRouter(prefix="/profile", tags=["profile"])

# field -> max length. One table, so the validator and the column widths cannot
# drift apart into a 500 from the database.
LIMITS: dict[str, int] = {
    "display_name": 80,
    "organization": 120,
    "role": 80,
    "use_case": 400,
}

# Control characters have no place in a display name and are how a plausible
# name smuggles a line break into a log or a CSV. Tabs and newlines included:
# these are single-line fields.
_CONTROL = frozenset(chr(c) for c in range(32)) | {"\x7f"}


class ProfileIn(BaseModel):
    """Every field optional — a PATCH may carry any subset.

    `None` is a meaningful value: it clears the field. An absent key leaves it
    alone. `model_fields_set` is what tells the two apart, so the model must not
    declare defaults that would make an omission look like an explicit null.
    """

    display_name: str | None = Field(default=None)
    organization: str | None = Field(default=None)
    role: str | None = Field(default=None)
    use_case: str | None = Field(default=None)


class ProfileOut(BaseModel):
    display_name: str | None = None
    organization: str | None = None
    role: str | None = None
    use_case: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    # so a client can tell "never filled in" from "filled in and cleared"
    exists: bool = False


def validate(field: str, value: Any) -> tuple[str | None, str | None]:
    """(cleaned, error). Rejects rather than coerces; only outer space is cut.

    Trimming surrounding whitespace is the one liberty taken, because a trailing
    space is a typing artefact rather than something the user meant. Everything
    else that fails is returned as an error for the caller to see and fix.
    """
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "must be text"
    cleaned = value.strip()
    if not cleaned:
        return None, None                       # blank clears the field
    if len(cleaned) > LIMITS[field]:
        return None, f"must be {LIMITS[field]} characters or fewer (got {len(cleaned)})"
    if any(ch in _CONTROL for ch in cleaned):
        return None, "must not contain line breaks or control characters"
    return cleaned, None


def _row(db: Session, user_id: int) -> Any:
    return db.execute(
        select(user_profiles).where(user_profiles.c.user_id == user_id)
    ).mappings().first()


def _out(row: Any) -> ProfileOut:
    if row is None:
        return ProfileOut(exists=False)
    return ProfileOut(
        display_name=row["display_name"],
        organization=row["organization"],
        role=row["role"],
        use_case=row["use_case"],
        created_at=iso_utc(row["created_at"]),
        updated_at=iso_utc(row["updated_at"]),
        exists=True,
    )


@router.get("", response_model=ProfileOut)
def read_profile(
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileOut:
    """The caller's own profile. There is no path to anyone else's.

    No id is accepted from the client — the row is selected by the user id on
    the verified credential, so there is nothing to enumerate. An account that
    has never saved one gets an empty profile rather than a 404: "not filled in"
    is a normal state, not an error.
    """
    return _out(_row(db, user.id))


@router.patch("", response_model=ProfileOut)
def update_profile(
    body: ProfileIn,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileOut:
    """Update the fields present in the body. Absent keys are left alone.

    Every field is validated before anything is written, and a single bad field
    rejects the whole request with per-field reasons. A partial write would
    leave the user unable to tell which half of their edit survived.
    """
    submitted = {k: getattr(body, k) for k in body.model_fields_set if k in LIMITS}
    if not submitted:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"error": "no recognised fields to update",
             "allowed": sorted(LIMITS)},
        )

    values: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for field, raw in submitted.items():
        cleaned, error = validate(field, raw)
        if error:
            errors[field] = error
        else:
            values[field] = cleaned
    if errors:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"error": "profile rejected", "fields": errors},
        )

    now = datetime.now(timezone.utc)
    existing = _row(db, user.id)
    if existing is None:
        db.execute(user_profiles.insert().values(
            user_id=user.id, created_at=now, updated_at=now, **values,
        ))
    else:
        db.execute(
            user_profiles.update()
            .where(user_profiles.c.user_id == user.id)   # scoped, always
            .values(updated_at=now, **values)
        )
    db.commit()
    return _out(_row(db, user.id))
