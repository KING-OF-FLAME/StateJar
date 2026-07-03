"""Users table definition (matches db/migrations/001_init.sql)."""

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table

auth_metadata = MetaData()

users = Table(
    "users",
    auth_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String(255), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("created_at", DateTime, nullable=False),
)
