"""SQLAlchemy engine / session wiring.

React → FastAPI → Services/ML → PostgreSQL.  Only this layer touches the DB.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

if settings.db_url.startswith("sqlite"):
    engine = create_engine(
        settings.db_url,
        future=True,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(
        settings.db_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator["SessionLocal"]:  # type: ignore[valid-type]
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
