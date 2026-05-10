"""Database engine, session, and base model configuration."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# SQLite needs `check_same_thread=False` so a single connection can be reused
# across threads (FastAPI's threadpool model). Other dialects (Postgres etc.)
# reject this option, so apply it only when the URL is SQLite.
_sqlite = settings.DATABASE_URL.startswith("sqlite")
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if _sqlite else {},
    pool_pre_ping=True,
)

# expire_on_commit=False so detached instances (e.g. the User cached on the
# WebSocket handler across multiple commits) keep their attributes readable
# without re-fetch. Without this, accessing user.id from a long-lived WS
# handler after a commit raises DetachedInstanceError.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


def get_db():
    """Dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
