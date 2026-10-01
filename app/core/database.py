"""
Database engine + session factory.

SQLAlchemy is the ORM: it lets us define tables as Python classes
instead of writing raw SQL for every operation.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """All table models inherit from this."""


def get_db():
    """FastAPI dependency: gives each request its own DB session, always closed after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()