import asyncio
from app.database import get_db, engine, Base
from sqlalchemy import text

async def test_connection():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("Tables created successfully.")
        
        async for session in get_db():
            result = await session.execute(text("SELECT 1"))
            print(f"Database connection test: {result.scalar()}")
            break
            
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
