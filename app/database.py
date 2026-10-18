from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from .config import settings

url = settings.database_url
if url.startswith("postgres://"):            # Neon/Heroku style -> SQLAlchemy style
    url = "postgresql://" + url[len("postgres://"):]

if url.startswith("sqlite"):
    engine = create_engine(url, connect_args={"check_same_thread": False})
else:
    # Serverless (Vercel): no long-lived pool; Neon's pooler (PgBouncer) handles connections.
    engine = create_engine(url, poolclass=NullPool, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
