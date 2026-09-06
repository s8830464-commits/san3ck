from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from bot.config import settings
from bot.database.models import Base

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency / context provider for async database session."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Create tables if they do not exist, and ensure schema migrations/columns."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safe add column 'section' if not exists for SQLite
        try:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE notes ADD COLUMN section VARCHAR(50);"))
        except Exception:
            pass
