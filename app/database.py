from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

# Construct database URL
# Assuming settings has DATABASE_URL, or constructing it from parts
# If not in settings, we might need to update config.py or Add it here
# For now, I'll use the hardcoded one I setup, but ideally it should be in env
DATABASE_URL = "postgresql+asyncpg://leads_user:leads_password@localhost/leads_auto_db"

engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
