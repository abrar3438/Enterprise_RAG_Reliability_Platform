"""Create all tables. Run once: python -m scripts.init_db"""
from sqlalchemy import text

from app.core.database import Base, engine
from app.models import tables  # noqa: F401  (import registers the models)

with engine.begin() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

Base.metadata.create_all(engine)
print("Tables created:", list(Base.metadata.tables.keys()))