"""Database utilities for async SQLAlchemy engine and session management."""
import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

# Use DATABASE_URL from environment (for Railway), fallback to SQLite for local dev
db_url = os.getenv('DATABASE_URL')
if db_url:
    # Railway provides a sync Postgres URL; convert to async for SQLAlchemy
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql+asyncpg://', 1)
    elif db_url.startswith('postgresql://'):
        db_url = db_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
    DATABASE_URL = db_url
else:
    DATABASE_URL = 'sqlite+aiosqlite:///forum.db'

engine = create_async_engine(DATABASE_URL, echo=True, future=True)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db():
    """Yield an async database session."""
    async with AsyncSessionLocal() as session:
        yield session 